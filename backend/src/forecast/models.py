"""예측 결과 자료구조.

contracts/api-spec.yaml 의 SimulationResponse 와 대응하지만 API 스키마를
그대로 쓰지 않는다. 예측 모듈은 HTTP 도 Pydantic 도 알 필요가 없고,
단위 테스트가 목 없이 돌아가야 한다. 응답 변환은 API 계층이 한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ScenarioLevel(StrEnum):
    """contracts/types.ts 의 ScenarioLevel 과 값이 같아야 한다.

    화면 표기는 여유 / 보통 / 빠듯이다. 낙관·기본·비관은 내부 용어이므로
    이 이름을 그대로 쓰지 않는다.
    """

    COMFORTABLE = "COMFORTABLE"
    NORMAL = "NORMAL"
    TIGHT = "TIGHT"


class PurchasePaymentType(StrEnum):
    """검토 중인 지출의 결제 방식. schema.sql 의 CHECK 제약과 값이 같다."""

    LUMP = "LUMP"
    INSTALLMENT = "INSTALLMENT"
    INTEREST_FREE = "INTEREST_FREE"


@dataclass(frozen=True, slots=True)
class PlannedPurchase:
    """아직 하지 않은 지출. "이거 사도 될까"에 답하기 위한 입력이다.

    할부면 원금을 개월 수로 나눠 매달 청구한다. 이자는 반영하지 않는다 —
    카드사·상품마다 다르고 규칙 테이블에 없는 값이라, 없는 숫자를 지어내는
    대신 원금만 다룬다. 무이자 할부는 정의상 이자가 없다.
    """

    amount: int
    payment_type: PurchasePaymentType = PurchasePaymentType.LUMP
    installment_months: int = 0

    def __post_init__(self) -> None:
        if self.amount <= 0:
            raise ValueError(f"지출 금액은 양수여야 합니다: {self.amount}")
        if self.payment_type is PurchasePaymentType.LUMP:
            if self.installment_months != 0:
                raise ValueError("일시불에 할부 개월이 지정되었습니다")
        elif self.installment_months <= 0:
            raise ValueError("할부 거래에 할부 개월이 없습니다")

    def monthly_charge(self) -> int:
        """월 청구액. 일시불이면 첫 달에 전액이므로 그대로 반환한다."""
        if self.payment_type is PurchasePaymentType.LUMP:
            return self.amount
        # 나머지를 버리면 총액이 원금보다 작아진다. 마지막 달 보정은
        # charge_schedule 에서 처리하고 여기서는 기본 월 청구액만 낸다.
        return self.amount // self.installment_months


@dataclass(frozen=True, slots=True)
class MonthlyPoint:
    """월말 잔고. month 는 'YYYY-MM'."""

    month: str
    balance: int


@dataclass(frozen=True, slots=True)
class Scenario:
    level: ScenarioLevel
    points: list[MonthlyPoint] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class DeadPoint:
    """잔고가 음수로 전환되는 첫 시점."""

    month: str
    level: ScenarioLevel
    shortage: int


@dataclass(frozen=True, slots=True)
class ForecastMeta:
    """예측 신뢰도를 이용자가 스스로 판단할 수 있게 하는 근거.

    숫자만 보여주고 근거를 감추면, 표본이 한 달뿐일 때도 6개월치 예측이
    같은 확신으로 보인다.
    """

    months_used: int
    txn_count: int
    cold_start: bool


@dataclass(frozen=True, slots=True)
class CashflowForecast:
    scenarios: list[Scenario]
    dead_point: DeadPoint | None
    meta: ForecastMeta
