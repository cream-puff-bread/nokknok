"""응답 모델.

필드명은 contracts/api-spec.yaml 과 contracts/types.ts 의 camelCase 를 따른다.
파이썬 쪽은 snake_case 로 쓰고 직렬화 시점에 alias 로 변환한다. 양쪽에서
같은 이름을 두 번 적지 않기 위해서다.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from src.adapter.base import ExpenseType
from src.api.query_parser import MAX_QUERY_LENGTH
from src.forecast import PurchasePaymentType, ScenarioLevel


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


# ─────────────────────────────────────────────
# 시뮬레이션
# ─────────────────────────────────────────────
class SimulateRequest(CamelModel):
    persona_id: int
    # 상한을 두는 이유는 긴 문장이 런타임 예산을 넘기기 쉽고 비용도 늘기
    # 때문이다. 화면 입력란도 같은 값으로 제한한다.
    query: str = Field(min_length=1, max_length=MAX_QUERY_LENGTH)


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
