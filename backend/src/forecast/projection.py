"""잔고 추이 산출.

변동 지출 예측(variable_spend)에 확정 지출과 수입을 얹어 월말 잔고를 그린다.
LLM 도 DB 도 쓰지 않는다 — 입력은 어댑터가 정규화한 FinancialSnapshot 하나뿐이고
같은 입력이면 항상 같은 결과가 나온다.

## 첫 점이 다음 달이 아니라 이번 달인 이유

이용자가 "지금 사도 될까"를 묻는 시점은 달 중간이다. 첫 점을 다음 달로 잡으면
이번 달 남은 확정 지출과 급여가 어디에도 반영되지 않아, 정작 가장 가까운
위험을 건너뛴다. 이 서비스가 막으려는 상황이 "월말에 이르러서야 자금 부족을
확인"하는 것이므로 이번 달 말이 첫 점이어야 한다.

이번 달은 이미 지난 날짜가 있으므로 남은 몫만 센다.
- 확정 지출: 청구일이 아직 오지 않은 항목만
- 급여: 급여일이 아직 오지 않았을 때만
- 변동 지출: 남은 일수 비율만큼. 일 단위 소비 패턴(급여일 직후 증가 등)까지
  반영하려면 표본이 훨씬 많아야 해서, 여기서는 일수 비례로만 나눈다.
"""

from __future__ import annotations

import calendar
from collections.abc import Iterable
from datetime import date

from src.adapter.base import FinancialSnapshot, FixedExpense
from src.common.logging import get_logger
from src.forecast.models import (
    CashflowForecast,
    DeadPoint,
    ForecastMeta,
    MonthlyPoint,
    PlannedPurchase,
    PurchasePaymentType,
    Scenario,
    ScenarioLevel,
)
from src.forecast.variable_spend import forecast_variable_spend

logger = get_logger(__name__)

DEFAULT_HORIZON_MONTHS = 6


def _shift_month(anchor: date, offset: int) -> tuple[int, int]:
    total = anchor.year * 12 + (anchor.month - 1) + offset
    return total // 12, total % 12 + 1


def _month_label(anchor: date, offset: int) -> str:
    year, month = _shift_month(anchor, offset)
    return f"{year:04d}-{month:02d}"


def _remaining_month_ratio(today: date) -> float:
    """이번 달 남은 일수 비율. 마지막 날이면 0 이 된다."""
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    return (days_in_month - today.day) / days_in_month


def _fixed_schedule(
    expenses: Iterable[FixedExpense], *, today: date, months: int
) -> list[int]:
    """offset 별 확정 지출 합계.

    remaining_months 는 오늘 기준 남은 청구 횟수다. 이번 달 청구일이 이미
    지났으면 이번 달은 청구되지 않고 남은 횟수도 줄지 않는다. 할부가 끝나면
    그 달부터 빠지는데, 이 감소를 반영하지 않으면 할부가 겹친 이용자의
    몇 달 뒤 잔고가 실제보다 낮게 나온다 — 이 서비스가 보여주려는 회복
    시점이 통째로 사라진다.
    """
    schedule = [0] * months
    for expense in expenses:
        left = expense.remaining_months
        for offset in range(months):
            charged_this_month = offset > 0 or expense.charge_day > today.day
            if not charged_this_month:
                continue
            if left is not None and left <= 0:
                break
            schedule[offset] += expense.amount
            if left is not None:
                left -= 1
    return schedule


def _purchase_schedule(
    purchase: PlannedPurchase | None, *, months: int
) -> list[int]:
    """검토 중인 지출의 offset 별 청구액. 구매는 이번 달(offset 0)에 한다."""
    schedule = [0] * months
    if purchase is None:
        return schedule

    if purchase.payment_type is PurchasePaymentType.LUMP:
        schedule[0] = purchase.amount
        return schedule

    monthly = purchase.monthly_charge()
    total_months = purchase.installment_months
    for offset in range(min(total_months, months)):
        schedule[offset] = monthly
    # 나눗셈에서 버린 나머지를 마지막 회차에 얹는다. 그냥 두면 청구 총액이
    # 원금보다 적어져 할부가 실제보다 유리해 보인다.
    last = total_months - 1
    if last < months:
        schedule[last] += purchase.amount - monthly * total_months
    return schedule


def _income_schedule(snapshot: FinancialSnapshot, *, today: date, months: int) -> list[int]:
    schedule = [snapshot.monthly_income] * months
    if snapshot.income_day <= today.day:
        # 이번 달 급여일이 지났다면 그 돈은 이미 account_balance 에 들어 있다.
        schedule[0] = 0
    return schedule


def _find_dead_point(scenarios: list[Scenario]) -> DeadPoint | None:
    """가장 이른 적자 전환 시점.

    같은 달에 여러 시나리오가 음수가 되면 부족액이 가장 큰 쪽을 고른다.
    화면에는 하나만 표시하므로, 덜 나쁜 쪽을 보여주면 위험을 축소해 전달하게 된다.
    """
    candidates: list[tuple[str, int, ScenarioLevel]] = []
    for scenario in scenarios:
        for point in scenario.points:
            if point.balance < 0:
                candidates.append((point.month, -point.balance, scenario.level))
                break

    if not candidates:
        return None

    earliest = min(month for month, _, _ in candidates)
    same_month = [c for c in candidates if c[0] == earliest]
    month, shortage, level = max(same_month, key=lambda c: c[1])
    return DeadPoint(month=month, level=level, shortage=shortage)


def forecast_cashflow(
    snapshot: FinancialSnapshot,
    *,
    today: date | None = None,
    months: int = DEFAULT_HORIZON_MONTHS,
    purchase: PlannedPurchase | None = None,
) -> CashflowForecast:
    """월말 잔고를 시나리오 세 가지로 그린다."""
    today = today or date.today()
    if months < 1:
        raise ValueError(f"예측 개월 수는 1 이상이어야 합니다: {months}")

    spend = forecast_variable_spend(snapshot.transactions, today=today)
    fixed = _fixed_schedule(snapshot.fixed_expenses, today=today, months=months)
    income = _income_schedule(snapshot, today=today, months=months)
    purchase_charges = _purchase_schedule(purchase, months=months)
    partial_ratio = _remaining_month_ratio(today)

    scenarios: list[Scenario] = []
    for level in ScenarioLevel:
        monthly_variable = spend.by_level[level]
        balance = snapshot.account_balance
        points: list[MonthlyPoint] = []
        for offset in range(months):
            variable = (
                round(monthly_variable * partial_ratio) if offset == 0 else monthly_variable
            )
            balance += income[offset] - fixed[offset] - variable - purchase_charges[offset]
            points.append(MonthlyPoint(month=_month_label(today, offset), balance=balance))
        scenarios.append(Scenario(level=level, points=points))

    dead_point = _find_dead_point(scenarios)
    if dead_point is not None:
        logger.info(
            "적자 전환 예상 month=%s level=%s 부족액=%d",
            dead_point.month,
            dead_point.level,
            dead_point.shortage,
        )

    return CashflowForecast(
        scenarios=scenarios,
        dead_point=dead_point,
        meta=ForecastMeta(
            months_used=spend.months_used,
            txn_count=spend.txn_count,
            cold_start=spend.cold_start,
        ),
    )
