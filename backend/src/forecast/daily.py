"""기준일부터 이번 달 말까지의 하루 단위 잔고.

달력 화면이 "이 날 위험" 을 표시하려면 그날의 잔고가 있어야 하는데,
forecast_cashflow 는 월말 값만 준다. 그렇다고 프론트에서 계산하게 두면
같은 화면 안에서 그래프와 달력이 서로 다른 말을 하게 된다 — 청구 여부의
경계가 `charge_day > today.day`, 급여는 `income_day <= today.day` 로
서로 반대 방향이라 옮겨 적다가 하루씩 어긋나기 쉽다.

그래서 여기서 계산한다. projection.py 와 같은 경계 규칙을 쓰며,
**마지막 날 값이 forecast_cashflow 의 첫 예측점(보통 시나리오)과 정확히
일치한다** — tests/test_forecast_daily.py 가 그것을 강제한다. 두 화면이
같은 달의 끝을 다른 숫자로 말하면 어느 쪽도 못 믿게 된다.

변동 지출은 남은 기간 총액을 남은 날수로 고르게 편다. 요일·월급일 효과가
있다는 건 알지만(generate_persona.py 가 그렇게 만든다) 그 분포를 여기서
다시 추정하면 근거 없는 곡선이 된다. 고르게 펴는 것이 "모른다" 를 그리는
가장 정직한 방법이고, 총액은 예측과 같다.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

from src.adapter.base import FinancialSnapshot, PaymentType
from src.forecast.models import ScenarioLevel
from src.forecast.variable_spend import forecast_variable_spend


@dataclass(frozen=True)
class DayBalance:
    day: int
    balance: int
    """그날 들어오는 돈. 급여일에만 0 이 아니다."""
    income: int
    """그날 빠지는 확정 지출 합계. 변동 지출은 포함하지 않는다."""
    fixed_outflow: int


def month_outlook(snapshot: FinancialSnapshot, *, today: date) -> list[DayBalance]:
    """기준일부터 이번 달 마지막 날까지, 하루씩의 예상 잔고.

    첫 항목은 기준일이며 잔고는 통장 잔액 그대로다. 그날까지의 일은 이미
    통장에 반영돼 있다.
    """
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    remaining_days = days_in_month - today.day

    variable_by_day = _spread_variable(snapshot, today=today, remaining_days=remaining_days)
    installment_by_day = _installments_by_day(snapshot, today=today)

    balance = snapshot.account_balance
    points = [
        DayBalance(day=today.day, balance=balance, income=0, fixed_outflow=0)
    ]

    for offset, day in enumerate(range(today.day + 1, days_in_month + 1)):
        # 급여일이 오늘이거나 지났으면 그 돈은 이미 통장 잔액에 있다
        # (projection.py 의 _income_schedule 과 같은 경계다).
        income = snapshot.monthly_income if snapshot.income_day == day else 0

        # 청구일이 오늘이면 이미 나간 것으로 본다 — _fixed_schedule 의
        # `charge_day > today.day` 와 같은 경계다. 여기만 >= 로 적으면
        # 달력이 그래프보다 하루치를 더 빼게 된다.
        fixed_outflow = sum(
            expense.amount
            for expense in snapshot.fixed_expenses
            if expense.charge_day == day
            and (expense.remaining_months is None or expense.remaining_months > 0)
        ) + installment_by_day.get(day, 0)

        balance += income - fixed_outflow - variable_by_day[offset]
        points.append(
            DayBalance(
                day=day, balance=balance, income=income, fixed_outflow=fixed_outflow
            )
        )

    return points


def _installments_by_day(snapshot: FinancialSnapshot, *, today: date) -> dict[int, int]:
    """이미 결제한 할부 중 이번 달에 남은 회차를 청구일에 붙인다.

    projection.py 의 _transaction_installment_schedule 이 offset 0 에 넣는 것과
    같은 금액을, 합계가 아니라 날짜별로 돌려준다. 청구일은 거래일과 같다고 보는
    것도 그쪽과 같은 가정이다.
    """
    anchor = today.year * 12 + (today.month - 1)
    by_day: dict[int, int] = {}

    for txn in snapshot.transactions:
        if txn.payment_type is PaymentType.LUMP or txn.installment_months <= 0:
            continue
        if txn.txn_date.day <= today.day:
            continue

        round_no = anchor - (txn.txn_date.year * 12 + (txn.txn_date.month - 1))
        if round_no < 0 or round_no >= txn.installment_months:
            continue

        monthly = txn.amount // txn.installment_months
        amount = monthly
        if round_no == txn.installment_months - 1:
            amount += txn.amount - monthly * txn.installment_months
        by_day[txn.txn_date.day] = by_day.get(txn.txn_date.day, 0) + amount

    return by_day


def _spread_variable(
    snapshot: FinancialSnapshot, *, today: date, remaining_days: int
) -> list[int]:
    """남은 변동 지출 총액을 남은 날에 고르게 나눈다.

    총액은 projection.py 가 첫 달에 쓰는 값과 같은 방식으로 구한다
    (월 추정치 x 남은 날 비율). 나눗셈에서 버린 나머지는 마지막 날에 얹어,
    합계가 예측의 첫 달 값과 1원도 어긋나지 않게 한다.
    """
    if remaining_days <= 0:
        return []

    days_in_month = calendar.monthrange(today.year, today.month)[1]
    spend = forecast_variable_spend(snapshot.transactions, today=today)
    monthly = spend.by_level[ScenarioLevel.NORMAL]
    total = round(monthly * (remaining_days / days_in_month))

    per_day = total // remaining_days
    schedule = [per_day] * remaining_days
    schedule[-1] += total - per_day * remaining_days
    return schedule
