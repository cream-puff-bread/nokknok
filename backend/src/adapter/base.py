"""거래 데이터 소스 추상화.

금융분야 마이데이터 표준 API 규격의 응답 형식에 맞춰 DTO를 정의하고,
조회 계층을 프로토콜로 분리한다. 상위 로직(엔진, 예측 모듈, API)은
어떤 구현체가 붙었는지 알지 못해야 한다.

구현체는 셋이다.

| 구현체              | 용도                                    |
|---------------------|-----------------------------------------|
| MockProvider        | MVP 시연. 가상 페르소나 데이터           |
| FileProvider        | 이용자가 카드사에서 내려받은 파일 업로드 |
| MyDataProvider      | 사업화 단계. 실제 연동                   |

MVP 단계에서 실제 연동에는 본인신용정보관리업 허가가 필요하므로
MyDataProvider 는 구현하지 않는다. 다만 이 프로토콜을 만족하도록
설계해 두면 구현체 교체만으로 전환이 완료된다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Protocol, runtime_checkable


class PaymentType(StrEnum):
    """결제 방식. contracts/schema.sql 의 CHECK 제약과 값이 일치해야 한다."""

    LUMP = "LUMP"
    INSTALLMENT = "INSTALLMENT"
    INTEREST_FREE = "INTEREST_FREE"


class ExpenseType(StrEnum):
    """확정 지출 유형."""

    SUBSCRIPTION = "SUBSCRIPTION"
    INSTALLMENT = "INSTALLMENT"
    LOAN = "LOAN"
    INSURANCE = "INSURANCE"


@dataclass(frozen=True, slots=True)
class CardRef:
    """이용자가 보유한 카드."""

    card_id: int
    issuer: str
    name: str
    payment_day: int
    is_demo: bool = False


@dataclass(frozen=True, slots=True)
class Transaction:
    """카드 승인 내역 또는 계좌 거래.

    amount 는 원 단위 정수이며 지출이 양수다.
    실수형을 쓰지 않는 이유는 금액 비교와 합산에서 오차가 누적되기 때문이다.
    """

    txn_date: date
    merchant: str
    amount: int
    category: str
    payment_type: PaymentType
    card_id: int | None = None
    installment_months: int = 0
    is_recurring: bool = False

    def __post_init__(self) -> None:
        if self.payment_type is PaymentType.LUMP and self.installment_months != 0:
            raise ValueError("일시불 거래에 할부 개월이 지정되었습니다")
        if self.payment_type is not PaymentType.LUMP and self.installment_months <= 0:
            raise ValueError("할부 거래에 할부 개월이 없습니다")


@dataclass(frozen=True, slots=True)
class FixedExpense:
    """지출이 확정된 항목. 금액과 날짜가 이미 정해져 있다."""

    expense_type: ExpenseType
    label: str
    amount: int
    charge_day: int
    remaining_months: int | None = None
    last_used_date: date | None = None
    card_id: int | None = None

    @property
    def unused_suspect(self) -> bool:
        """미사용 의심 구독인지 판단한다.

        구독이면서 최근 사용 기록이 90일 이상 없으면 해지를 권할 대상으로 본다.
        기준일을 인자로 받지 않고 today 를 쓰는 이유는 이 값이 화면 표시용이며
        계산에는 관여하지 않기 때문이다.
        """
        if self.expense_type is not ExpenseType.SUBSCRIPTION:
            return False
        if self.last_used_date is None:
            return False
        return (date.today() - self.last_used_date).days >= 90


@dataclass(frozen=True, slots=True)
class FinancialSnapshot:
    """한 이용자의 금융 상태 전체.

    데이터 소스가 무엇이든 이 형태로 정규화해 반환한다.
    """

    account_balance: int
    monthly_income: int
    income_day: int
    cards: list[CardRef] = field(default_factory=list)
    transactions: list[Transaction] = field(default_factory=list)
    fixed_expenses: list[FixedExpense] = field(default_factory=list)

    @property
    def fixed_total(self) -> int:
        """월 확정 지출 합계."""
        return sum(e.amount for e in self.fixed_expenses)

    @property
    def available_balance(self) -> int:
        """가용잔고.

        통장 잔고에서 확정 지출을 뺀 실제 사용 가능 금액이다.
        음수가 될 수 있으며, 이 경우 이미 자금이 부족한 상태다.
        """
        return self.account_balance - self.fixed_total


@runtime_checkable
class TransactionProvider(Protocol):
    """거래 데이터 조회 인터페이스.

    상위 계층은 이 프로토콜에만 의존한다.
    구현체를 교체해도 엔진과 예측 모듈은 수정할 필요가 없다.
    """

    def fetch(self, source_key: str) -> FinancialSnapshot:
        """source_key 에 해당하는 금융 상태를 조회한다.

        source_key 의 의미는 구현체마다 다르다.
        MockProvider 는 페르소나 code, FileProvider 는 업로드 파일 경로다.
        """
        ...
