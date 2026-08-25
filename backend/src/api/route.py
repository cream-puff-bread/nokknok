"""결제 라우팅 최적화 엔드포인트.

계산은 src/engine/route.py가 전담한다(엔진은 LLM·RAG를 모른다). 여기서는
요청 검증, DB·어댑터 조회, ruleId→근거 조항 조인, 응답 조립만 한다.

explanation은 항상 null이다. LLM 설명 생성(런타임 프로파일, 3.5초 예산)을
연결하는 건 프롬프트 설계가 필요한 별도 작업이라 이번 범위에서 뺐다 —
계약상 explanation=null은 허용된 상태이므로(CLAUDE.md), 숫자 결과를
막지 않고 우선 내보낸다.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import asdict
from datetime import date
from typing import Annotated, TypeVar

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.adapter.factory import SourceKind, build_provider
from src.api.deps import get_db_session
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
from src.common.logging import get_logger
from src.engine.route import RouteCandidate, evaluate_route
from src.repository import card as card_repo
from src.repository import category as category_repo
from src.repository import clause as clause_repo
from src.repository import persona as persona_repo

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["route"])

SessionDep = Annotated[Session, Depends(get_db_session)]

_T = TypeVar("_T")


def _group_by_card_id(rows: list[_T]) -> dict[int, list[_T]]:
    grouped: dict[int, list[_T]] = defaultdict(list)
    for row in rows:
        grouped[row.card_id].append(row)  # type: ignore[attr-defined]
    return dict(grouped)


def _candidate_response(candidate: RouteCandidate) -> RouteCandidateResponse:
    return RouteCandidateResponse(**asdict(candidate))


@router.post("/route", response_model=RouteResponse, summary="결제 라우팅 최적화")
def route_payment(session: SessionDep, body: RouteRequest) -> RouteResponse:
    if body.amount <= 0:
        raise InvalidAmountError(body.amount)

    valid_categories = set(category_repo.list_category_codes(session))
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

    started = time.perf_counter()
    result = evaluate_route(
        owned_cards=snapshot.cards,
        cards_by_id=cards_by_id,
        rules_by_card=rules_by_card,
        exclusions_by_card=exclusions_by_card,
        transactions=snapshot.transactions,
        amount=body.amount,
        category=body.category,
        as_of=date.today(),
    )
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    rule_clause_id = {
        rule.id: rule.clause_id for rules in rules_by_card.values() for rule in rules
    }
    best_clause_id = (
        rule_clause_id.get(result.best.rule_id) if result.best.rule_id is not None else None
    )
    clause = clause_repo.get_clause(session, best_clause_id) if best_clause_id else None

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
            explanation=None,
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
