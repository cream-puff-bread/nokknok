"""응답 모델.

필드명은 contracts/api-spec.yaml 과 contracts/types.ts 의 camelCase 를 따른다.
파이썬 쪽은 snake_case 로 쓰고 직렬화 시점에 alias 로 변환한다. 양쪽에서
같은 이름을 두 번 적지 않기 위해서다.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from src.adapter.base import ExpenseType


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
