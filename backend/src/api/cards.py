"""보유 카드 현황 엔드포인트.

카드사 앱은 "이번 달 얼마 썼는지" 는 알려주지만 "그래서 어떤 혜택이
열렸는지", "무엇이 실적에서 빠지는지" 는 알려주지 않는다. 그 둘을 한
화면에 놓는 것이 이 엔드포인트의 목적이다.

실적은 engine.card_performance 를 그대로 쓴다. 여기서 따로 합산하면
결제 라우팅이 말하는 실적과 이 화면의 실적이 어긋날 수 있는데, 같은 값을
두 화면이 다르게 말하는 것이 이 서비스가 가장 하지 말아야 할 일이다
(CLAUDE.md: 금액 계산은 엔진이 전담한다).

검수 완료(verified=true) 규칙만 담는다. 검수 전 규칙이 화면에 뜨면
이용자가 받을 수 없는 혜택을 약속하는 셈이 된다.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from src.adapter.factory import SourceKind, build_provider
from src.api.deps import SessionDep
from src.api.schemas import CardBenefitResponse, CardExclusionResponse, OwnedCardResponse
from src.common.logging import get_logger
from src.engine.qualification import performance_period
from src.engine.route import card_performance
from src.repository import card as card_repo
from src.repository import category as category_repo
from src.repository import persona as persona_repo

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["cards"])

# 결제 방식은 schema.sql 의 CHECK 제약으로 값이 고정돼 있다(마스터 테이블이
# 아니라 DB 가 소유한 값 집합이 아니므로 여기서 표기만 붙인다).
_PAYMENT_TYPE_LABEL = {
    "LUMP": "일시불",
    "INSTALLMENT": "할부",
    "INTEREST_FREE": "무이자 할부",
}

WILDCARD_LABEL = "전체"


def _target_label(kind: str, value: str, category_labels: dict[str, str]) -> str:
    if kind == "CATEGORY":
        return category_labels.get(value, value)
    if kind == "PAYMENT_TYPE":
        return _PAYMENT_TYPE_LABEL.get(value, value)
    return value


@router.get("/cards", response_model=list[OwnedCardResponse], summary="보유 카드 현황")
def list_owned_cards(
    session: SessionDep,
    persona_id: Annotated[int, Query(alias="personaId", description="페르소나 id")],
) -> list[OwnedCardResponse]:
    code = persona_repo.get_persona_code(session, persona_id)
    snapshot = build_provider(SourceKind.MOCK, session=session).fetch(code)

    owned_ids = [c.card_id for c in snapshot.cards]
    cards = {c.id: c for c in card_repo.get_cards(session, owned_ids)}

    rules_by_card: dict[int, list] = {}
    for rule in card_repo.list_benefit_rules(session, owned_ids):
        if rule.verified:
            rules_by_card.setdefault(rule.card_id, []).append(rule)

    exclusions_by_card: dict[int, list] = {}
    for exclusion in card_repo.list_exclusions(session, owned_ids):
        if exclusion.verified:
            exclusions_by_card.setdefault(exclusion.card_id, []).append(exclusion)

    category_labels = {
        c.code: c.label for c in category_repo.list_categories(session)
    }
    category_labels.setdefault(category_repo.WILDCARD_CATEGORY, WILDCARD_LABEL)

    today = date.today()
    result: list[OwnedCardResponse] = []

    for owned in snapshot.cards:
        card = cards.get(owned.card_id)
        if card is None:
            continue

        start, end = performance_period(
            card.perf_period_type,
            today,
            payment_day=owned.payment_day,
            billing_offset_days=card.billing_offset_days,
        )
        # 기간 끝이 미래면 아직 지나지 않은 날의 지출을 0원으로 세게 된다.
        # 확정된 부분만 보여준다(engine/route.py 의 같은 판단과 맞춘다).
        exclusions = exclusions_by_card.get(card.id, [])
        perf = card_performance(
            snapshot.transactions, card.id, exclusions, start, min(end, today)
        )

        rules = sorted(
            rules_by_card.get(card.id, []), key=lambda r: (r.perf_min, r.category)
        )
        thresholds = [r.perf_min for r in rules]

        result.append(
            OwnedCardResponse(
                card_id=card.id,
                card_name=card.name,
                issuer=card.issuer,
                is_demo=card.is_demo,
                payment_day=owned.payment_day,
                perf_period_start=start,
                perf_period_end=end,
                perf_current=perf,
                perf_next_threshold=min(thresholds) if thresholds else None,
                monthly_cap=card.monthly_cap,
                benefits=[
                    CardBenefitResponse(
                        category=r.category,
                        category_label=category_labels.get(r.category, r.category),
                        perf_min=r.perf_min,
                        perf_max=r.perf_max,
                        discount_rate=float(r.discount_rate),
                        category_cap=r.category_cap,
                        active=r.perf_min <= perf
                        and (r.perf_max is None or perf < r.perf_max),
                    )
                    for r in rules
                ],
                exclusions=[
                    CardExclusionResponse(
                        exclusion_type=e.exclusion_type,
                        target_kind=e.target_kind,
                        target_value=e.target_value,
                        target_label=_target_label(
                            e.target_kind, e.target_value, category_labels
                        ),
                    )
                    for e in exclusions
                ],
            )
        )

    logger.info("보유 카드 조회 persona_id=%d 카드=%d장", persona_id, len(result))
    return result
