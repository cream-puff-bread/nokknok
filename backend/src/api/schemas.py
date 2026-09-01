"""응답 모델.

필드명은 contracts/api-spec.yaml 과 contracts/types.ts 의 camelCase 를 따른다.
파이썬 쪽은 snake_case 로 쓰고 직렬화 시점에 alias 로 변환한다. 양쪽에서
같은 이름을 두 번 적지 않기 위해서다.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

from src.adapter.base import ExpenseType, PaymentType
from src.api.query_parser import MAX_QUERY_LENGTH
from src.forecast import PurchasePaymentType, ScenarioLevel


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class SpendCategoryResponse(CamelModel):
    code: str
    label: str


class CardBenefitResponse(CamelModel):
    category: str
    category_label: str
    perf_min: int
    perf_max: int | None = None
    discount_rate: float
    category_cap: int | None = None
    active: bool


class CardExclusionResponse(CamelModel):
    exclusion_type: str
    target_kind: str
    target_value: str
    target_label: str


class OwnedCardResponse(CamelModel):
    card_id: int
    card_name: str
    issuer: str
    is_demo: bool
    payment_day: int
    perf_period_start: date
    perf_period_end: date
    perf_current: int
    perf_next_threshold: int | None = None
    monthly_cap: int | None = None
    benefits: list[CardBenefitResponse] = []
    exclusions: list[CardExclusionResponse] = []


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
    # 엔진(src/engine/route.py evaluate_route)이 "결제를 미루면 유리한지"
    # 비교하는 데 쓴다 — 없으면 오늘 결제 하나만 본다. 미래 지출을
    # 예측하지는 않는다: 마감일까지 이미 지난 부분의 실적만 확정으로
    # 세고, 아직 안 지난 구간은 0원으로도 근거 없는 값으로도 채우지 않는다.
    due_date: date | None = None


class ClauseRefResponse(CamelModel):
    content: str
    doc_name: str
    page_no: int | None = None


class RouteCandidateResponse(CamelModel):
    card_id: int
    card_name: str
    is_demo: bool
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
    is_demo: bool
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


# ─────────────────────────────────────────────
# 시뮬레이션
# ─────────────────────────────────────────────
class PurchaseInput(CamelModel):
    """구조화된 구매 정보. 응답의 ParsedQueryResponse 와 필드가 같다.

    결제 라우팅 화면은 금액·카테고리·결제 방식을 이미 정확히 알고 있다.
    그걸 문장으로 만들어 LLM 에 되읽히면 1.4초를 더 쓰고, 해석이 어긋나면
    두 화면이 서로 다른 숫자를 말하게 된다.
    """

    amount: int
    payment_type: PurchasePaymentType
    installment_months: int = 0
    category: str

    @model_validator(mode="after")
    def _check_installment(self) -> PurchaseInput:
        # PlannedPurchase 도 같은 불변식을 지키지만 그건 ValueError 라 500 이
        # 된다. 자연어 경로는 파서가 정규화해 이 조합이 안 나오는데, 구조화
        # 입력은 클라이언트가 그대로 보낼 수 있으므로 경계에서 막아 422 로
        # 돌려준다(CLAUDE.md: 모든 응답은 ErrorResponse 형식이다).
        if self.payment_type is PurchasePaymentType.LUMP:
            if self.installment_months != 0:
                raise ValueError("일시불에는 할부 개월을 지정할 수 없습니다")
        elif self.installment_months <= 0:
            raise ValueError("할부 결제에는 할부 개월이 필요합니다")
        return self


class SimulateRequest(CamelModel):
    persona_id: int
    # 상한을 두는 이유는 긴 문장이 런타임 예산을 넘기기 쉽고 비용도 늘기
    # 때문이다. 화면 입력란도 같은 값으로 제한한다.
    query: str | None = Field(default=None, min_length=1, max_length=MAX_QUERY_LENGTH)
    purchase: PurchaseInput | None = None

    @model_validator(mode="after")
    def _require_one_input(self) -> SimulateRequest:
        # 둘 다 없으면 무엇을 계산할지 알 수 없다. 스키마 단계에서 막아
        # 라우터가 None 을 다시 확인하지 않게 한다.
        if self.query is None and self.purchase is None:
            raise ValueError("query 와 purchase 중 하나는 있어야 합니다")
        return self


class ParsedQueryResponse(CamelModel):
    """LLM 이 질의를 어떻게 읽었는지 그대로 돌려준다.

    "180만원"을 180 으로 잘못 읽어도 코드가 알아낼 방법이 없다. 이용자가
    눈으로 확인하는 것이 유일하게 확실한 검증이라 응답에 포함한다.
    """

    amount: int
    payment_type: PurchasePaymentType
    installment_months: int
    category: str


class ScenarioPointResponse(CamelModel):
    month: str
    balance: int


class ScenarioResponse(CamelModel):
    level: ScenarioLevel
    points: list[ScenarioPointResponse]


class DeadPointResponse(CamelModel):
    month: str
    level: ScenarioLevel
    shortage: int


class ForecastMetaResponse(CamelModel):
    months_used: int
    txn_count: int
    cold_start: bool


class SimulationResponse(CamelModel):
    parsed: ParsedQueryResponse
    scenarios: list[ScenarioResponse]
    dead_point: DeadPointResponse | None
    forecast_meta: ForecastMetaResponse
