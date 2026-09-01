"""결제 라우팅 최적화 엔드포인트.

계산은 src/engine/route.py가 전담한다(엔진은 LLM·RAG를 모른다). 여기서는
요청 검증, DB·어댑터 조회, ruleId→근거 조항 조인, LLM 설명 생성, 응답
조립만 한다.

explanation은 런타임 LLM 프로파일(LLM_RUNTIME_TIMEOUT_BUDGET_MS)로
생성한다. 클라이언트는 get_explanation_client 의존성이 만들고, LLM_API_KEY가
비어 있으면 None을 돌려준다 — 실패가 뻔한 네트워크 호출로 예산을 낭비하지
않기 위해서다. 호출 실패든 클라이언트 부재든 explanation=None이 되고,
계산 결과(best 등)는 그대로 응답에 실린다(CLAUDE.md: LLM 실패 시에도
계산 결과는 반드시 응답에 포함된다).
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import asdict
from datetime import date, timedelta
from typing import Annotated, TypeVar

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.adapter.factory import SourceKind, build_provider
from src.api.deps import get_db_session, get_explanation_client
from src.api.explain import generate_explanation
from src.api.schemas import (
    ClauseRefResponse,
    ComputeMetaResponse,
    NewCardSuggestionResponse,
    RouteCandidateResponse,
    RouteOptionResponse,
    RouteRequest,
    RouteResponse,
)
from src.common.exceptions import InvalidAmountError, InvalidCategoryError
from src.common.llm import LlmClient
from src.common.logging import get_logger
from src.engine.route import RouteCandidate, evaluate_route
from src.repository import card as card_repo
from src.repository import category as category_repo
from src.repository import clause as clause_repo
from src.repository import persona as persona_repo

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["route"])

SessionDep = Annotated[Session, Depends(get_db_session)]
LlmDep = Annotated[LlmClient | None, Depends(get_explanation_client)]

# contracts/api-spec.yaml: RouteRequest.dueDate "생략 시 오늘부터 30일".
# 프론트가 아직 이 값을 안 보내는데(feat/route-result-screen), 계약의
# 기본값을 여기서 적용하지 않으면 엔진의 결제일 조합 탐색(evaluate_route의
# due_date)이 실제 화면에서는 영영 실행되지 않는다(하영님 리뷰, 2026-08-31).
DEFAULT_DUE_DATE_WINDOW_DAYS = 30

_T = TypeVar("_T")


def _group_by_card_id(rows: list[_T]) -> dict[int, list[_T]]:
    grouped: dict[int, list[_T]] = defaultdict(list)
    for row in rows:
        grouped[row.card_id].append(row)  # type: ignore[attr-defined]
    return dict(grouped)


def _candidate_response(candidate: RouteCandidate) -> RouteCandidateResponse:
    return RouteCandidateResponse(**asdict(candidate))


@router.post("/route", response_model=RouteResponse, summary="결제 라우팅 최적화")
def route_payment(session: SessionDep, llm: LlmDep, body: RouteRequest) -> RouteResponse:
    if body.amount <= 0:
        raise InvalidAmountError(body.amount)

    # list_category_codes()는 ALL(규칙 매칭용 와일드카드)까지 포함한다.
    # 결제 요청의 category는 실제 소비 카테고리여야 하므로 ALL을 뺀
    # list_purchase_category_codes()로 검증한다 — 안 그러면 category=ALL이
    # 그대로 엔진에 들어가 "카테고리 전용 규칙이 ALL보다 우선한다"는
    # 우선순위 규칙 자체가 의미를 잃는다(repository/category.py 참조).
    valid_categories = set(category_repo.list_purchase_category_codes(session))
    if body.category not in valid_categories:
        raise InvalidCategoryError(body.category)

    # personaId(int) <-> source_key(str) 변환은 API 계층의 책임이다
    # (repository/persona.py get_persona_code 참조, 팀 합의 사항).
    code = persona_repo.get_persona_code(session, body.persona_id)
    provider = build_provider(SourceKind.MOCK, session=session)
    snapshot = provider.fetch(code)

    # newCardSuggestion이 보유하지 않은 카드까지 비교해야 하므로 카탈로그
    # 전체를 가져온다 — engine/route.py의 evaluate_route는 owned_cards에
    # 없는 card_id를 후보로 세지 않으니 함께 넘겨도 안전하다.
    all_cards = card_repo.get_all_cards(session)
    all_card_ids = [c.id for c in all_cards]
    cards_by_id = {c.id: c for c in all_cards}
    rules_by_card = _group_by_card_id(card_repo.list_benefit_rules(session, all_card_ids))
    exclusions_by_card = _group_by_card_id(card_repo.list_exclusions(session, all_card_ids))

    as_of = date.today()
    due_date = body.due_date or as_of + timedelta(days=DEFAULT_DUE_DATE_WINDOW_DAYS)

    started = time.perf_counter()
    result = evaluate_route(
        owned_cards=snapshot.cards,
        cards_by_id=cards_by_id,
        rules_by_card=rules_by_card,
        exclusions_by_card=exclusions_by_card,
        transactions=snapshot.transactions,
        amount=body.amount,
        category=body.category,
        as_of=as_of,
        due_date=due_date,
    )
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    rule_by_id = {rule.id: rule for rules in rules_by_card.values() for rule in rules}
    best_rule = (
        rule_by_id.get(result.best.rule_id) if result.best.rule_id is not None else None
    )
    clause = (
        clause_repo.get_clause(session, best_rule.clause_id)
        if best_rule is not None and best_rule.clause_id is not None
        else None
    )

    explanation = None
    if llm is not None:
        explanation = generate_explanation(
            llm,
            result.best,
            best_rule,
            clause,
            body.category,
            body.amount,
        )
    else:
        logger.info("LLM 클라이언트 없음 — explanation 생성을 건너뜁니다")

    logger.info(
        "라우팅 판정 persona_id=%d best_card=%d discount=%d elapsed_ms=%d",
        body.persona_id,
        result.best.card_id,
        result.best.expected_discount,
        elapsed_ms,
    )

    return RouteResponse(
        best=RouteOptionResponse(
            **asdict(result.best),
            explanation=explanation,
            clauses=(
                [
                    ClauseRefResponse(
                        content=clause.content,
                        doc_name=clause.doc_name,
                        page_no=clause.page_no,
                    )
                ]
                if clause is not None
                else []
            ),
        ),
        alternatives=[_candidate_response(c) for c in result.alternatives],
        new_card_suggestion=(
            NewCardSuggestionResponse(
                card_name=result.new_card_suggestion.card_name,
                is_demo=result.new_card_suggestion.is_demo,
                expected_gain=result.new_card_suggestion.expected_gain,
                is_affiliate=result.new_card_suggestion.is_affiliate,
            )
            if result.new_card_suggestion is not None
            else None
        ),
        compute_meta=ComputeMetaResponse(
            candidates_total=result.compute_meta.candidates_total,
            candidates_pruned=result.compute_meta.candidates_pruned,
            elapsed_ms=elapsed_ms,
            excluded_unverified_cards=result.compute_meta.excluded_unverified_cards,
        ),
    )
