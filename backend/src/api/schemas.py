"""응답 모델.

필드명은 contracts/api-spec.yaml 과 contracts/types.ts 의 camelCase 를 따른다.
파이썬 쪽은 snake_case 로 쓰고 직렬화 시점에 alias 로 변환한다. 양쪽에서
같은 이름을 두 번 적지 않기 위해서다.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from src.adapter.base import ExpenseType, PaymentType


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class PersonaResponse(CamelModel):
    id: int
    code: str
    display_name: str
    description: str
    account_balance: int
    card_count: int


class FixedExpenseResponse(CamelModel):
    label: str
    amount: int
    charge_day: int
    expense_type: ExpenseType
    unused_suspect: bool


class BalanceResponse(CamelModel):
    account_balance: int
    fixed_total: int
    available_balance: int
    fixed_expenses: list[FixedExpenseResponse]


class RouteRequest(CamelModel):
    persona_id: int
    amount: int
    category: str
    # 엔진(src/engine/route.py)은 아직 이 값을 쓰지 않는다 — payDate 최적화는
    # 미래 지출 예측이 필요한데 forecast 모듈이 없어 지금은 항상 오늘 날짜로
    # 판정한다. 계약대로 받아두되 계산에는 반영하지 않는다는 걸 명시한다.
    due_date: date | None = None


class ClauseRefResponse(CamelModel):
    content: str
    doc_name: str
    page_no: int | None = None


class RouteCandidateResponse(CamelModel):
    card_id: int
    card_name: str
    pay_date: date
    payment_type: PaymentType
    installment_months: int
    expected_discount: int
    perf_achieved: bool
    perf_current: int
    perf_required: int
    rule_id: int | None = None


class RouteOptionResponse(RouteCandidateResponse):
    explanation: str | None = None
    clauses: list[ClauseRefResponse] = []


class NewCardSuggestionResponse(CamelModel):
    card_name: str
    expected_gain: int
    is_affiliate: bool


class ComputeMetaResponse(CamelModel):
    candidates_total: int
    candidates_pruned: int
    elapsed_ms: int
    excluded_unverified_cards: int


class RouteResponse(CamelModel):
    best: RouteOptionResponse
    alternatives: list[RouteCandidateResponse]
    new_card_suggestion: NewCardSuggestionResponse | None = None
    compute_meta: ComputeMetaResponse
