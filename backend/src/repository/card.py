"""카드·규칙·제외 조회.

card_benefit_rule / card_exclusion 원본 행을 그대로 가져오기만 한다.
어느 규칙을 적용할지 고르는 우선순위 판정(README "규칙 적용 우선순위")은
여기서 하지 않는다 — DB 없이 단위 테스트가 돌아야 하는
src/engine/qualification.py 가 그 책임을 진다.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session


@dataclass(frozen=True, slots=True)
class Card:
    id: int
    issuer: str
    name: str
    perf_period_type: str  # MONTH_START | BILLING_CYCLE
    billing_close_day: int | None
    monthly_cap: int | None
    is_demo: bool


@dataclass(frozen=True, slots=True)
class BenefitRule:
    id: int
    card_id: int
    perf_min: int
    perf_max: int | None
    category: str
    discount_rate: Decimal
    category_cap: int | None
    clause_id: int | None
    verified: bool


@dataclass(frozen=True, slots=True)
class Exclusion:
    id: int
    card_id: int
    exclusion_type: str  # PERFORMANCE | DISCOUNT | BOTH
    target_kind: str  # CATEGORY | MERCHANT | PAYMENT_TYPE
    target_value: str
    clause_id: int | None
    verified: bool


_CARD_SQL = text(
    """
    SELECT id, issuer, name, perf_period_type, billing_close_day, monthly_cap, is_demo
    FROM card
    WHERE id IN :card_ids
    ORDER BY id
    """
).bindparams(bindparam("card_ids", expanding=True))

_RULE_SQL = text(
    """
    SELECT id, card_id, perf_min, perf_max, category, discount_rate,
           category_cap, clause_id, verified
    FROM card_benefit_rule
    WHERE card_id IN :card_ids
    ORDER BY card_id, perf_min
    """
).bindparams(bindparam("card_ids", expanding=True))

_EXCLUSION_SQL = text(
    """
    SELECT id, card_id, exclusion_type, target_kind, target_value, clause_id, verified
    FROM card_exclusion
    WHERE card_id IN :card_ids
    ORDER BY card_id, id
    """
).bindparams(bindparam("card_ids", expanding=True))


def get_cards(session: Session, card_ids: list[int]) -> list[Card]:
    if not card_ids:
        return []
    rows = session.execute(_CARD_SQL, {"card_ids": card_ids}).mappings().all()
    return [
        Card(
            id=r["id"],
            issuer=r["issuer"],
            name=r["name"],
            perf_period_type=r["perf_period_type"],
            billing_close_day=r["billing_close_day"],
            monthly_cap=r["monthly_cap"],
            is_demo=r["is_demo"],
        )
        for r in rows
    ]


def list_benefit_rules(session: Session, card_ids: list[int]) -> list[BenefitRule]:
    """검수 여부와 무관하게 전부 가져온다.

    verified=false 행을 걸러내는 판단은 여기서 하지 않는다 — 후보 카드가
    전부 미검수라 판정 불가한 상황(NoVerifiedRuleError)을 엔진이 구분해야
    하므로, "규칙이 아예 없는 카드"와 "규칙은 있으나 미검수뿐인 카드"를
    구분할 수 있는 원본 그대로 넘긴다.
    """
    if not card_ids:
        return []
    rows = session.execute(_RULE_SQL, {"card_ids": card_ids}).mappings().all()
    return [
        BenefitRule(
            id=r["id"],
            card_id=r["card_id"],
            perf_min=r["perf_min"],
            perf_max=r["perf_max"],
            category=r["category"],
            discount_rate=r["discount_rate"],
            category_cap=r["category_cap"],
            clause_id=r["clause_id"],
            verified=r["verified"],
        )
        for r in rows
    ]


def list_exclusions(session: Session, card_ids: list[int]) -> list[Exclusion]:
    if not card_ids:
        return []
    rows = session.execute(_EXCLUSION_SQL, {"card_ids": card_ids}).mappings().all()
    return [
        Exclusion(
            id=r["id"],
            card_id=r["card_id"],
            exclusion_type=r["exclusion_type"],
            target_kind=r["target_kind"],
            target_value=r["target_value"],
            clause_id=r["clause_id"],
            verified=r["verified"],
        )
        for r in rows
    ]
