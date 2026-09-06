from datetime import date

import pytest

from src.adapter.base import (
    ExpenseType,
    FinancialSnapshot,
    FixedExpense,
    PaymentType,
    Transaction,
)
from src.forecast import ScenarioLevel, forecast_cashflow
from src.forecast.daily import month_outlook


def _variable_transactions() -> list[Transaction]:
    """변동 지출 추정이 0 이 아니게 만드는 최소 표본.

    이게 없으면 월말 일치 테스트가 나눗셈 나머지 배분을 전혀 건드리지 못해,
    보정을 통째로 지워도 통과한다(실제로 확인했다).
    """
    return [
        Transaction(
            txn_date=date(2026, month, day),
            merchant="가맹점",
            amount=40_000,
            category="DINING",
            payment_type=PaymentType.LUMP,
        )
        for month in (5, 6, 7)
        for day in (3, 11, 19, 27)
    ]


def _snapshot(**overrides) -> FinancialSnapshot:
    base = {
        "account_balance": 1_600_000,
        "monthly_income": 2_900_000,
        "income_day": 25,
        "fixed_expenses": [
            FixedExpense(
                label="구독",
                amount=17_000,
                charge_day=5,
                expense_type=ExpenseType.SUBSCRIPTION,
                remaining_months=None,
            ),
            FixedExpense(
                label="할부",
                amount=145_000,
                charge_day=25,
                expense_type=ExpenseType.INSTALLMENT,
                remaining_months=6,
            ),
            FixedExpense(
                label="대출",
                amount=530_000,
                charge_day=28,
                expense_type=ExpenseType.LOAN,
                remaining_months=12,
            ),
        ],
        "transactions": _variable_transactions(),
    }
    base.update(overrides)
    return FinancialSnapshot(**base)


class Test월말_일치:
    """달력 마지막 날과 그래프 첫 점이 같은 숫자여야 한다.

    두 화면이 같은 달의 끝을 다르게 말하면 어느 쪽도 못 믿게 된다. 이 서비스가
    한 번 겪은 실패(그래프 첫 점이 가용잔고라 기준이 어긋났던 것)와 같은 종류라
    회귀로 막는다.
    """

    @pytest.mark.parametrize("today", [date(2026, 8, 20), date(2026, 8, 1), date(2026, 8, 30)])
    def test_마지막_날이_예측_첫_달과_같다(self, today: date) -> None:
        snapshot = _snapshot()

        outlook = month_outlook(snapshot, today=today)
        forecast = forecast_cashflow(snapshot, today=today)
        normal = next(s for s in forecast.scenarios if s.level is ScenarioLevel.NORMAL)

        assert outlook[-1].balance == normal.points[0].balance

    def test_거래_할부가_있어도_일치한다(self) -> None:
        today = date(2026, 8, 20)
        snapshot = _snapshot(
            transactions=[
                *_variable_transactions(),
                Transaction(
                    txn_date=date(2026, 6, 27),
                    merchant="노트북",
                    amount=1_200_000,
                    category="ONLINE",
                    payment_type=PaymentType.INSTALLMENT,
                    installment_months=6,
                ),
            ]
        )

        outlook = month_outlook(snapshot, today=today)
        forecast = forecast_cashflow(snapshot, today=today)
        normal = next(s for s in forecast.scenarios if s.level is ScenarioLevel.NORMAL)

        assert outlook[-1].balance == normal.points[0].balance


class Test경계:
    def test_기준일은_통장_잔액_그대로다(self) -> None:
        snapshot = _snapshot()
        outlook = month_outlook(snapshot, today=date(2026, 8, 20))

        assert outlook[0].day == 20
        assert outlook[0].balance == snapshot.account_balance

    def test_기준일과_같은_청구일은_이미_나간_것으로_본다(self) -> None:
        """_fixed_schedule 의 `charge_day > today.day` 와 같은 경계.

        여기만 >= 로 적으면 달력이 그래프보다 하루치를 더 뺀다.
        """
        snapshot = _snapshot()
        outlook = month_outlook(snapshot, today=date(2026, 8, 25))

        assert all(p.fixed_outflow == 0 for p in outlook if p.day == 25)
        assert outlook[0].balance == snapshot.account_balance

    def test_급여일이_지났으면_이번_달_입금은_없다(self) -> None:
        snapshot = _snapshot(income_day=10)
        outlook = month_outlook(snapshot, today=date(2026, 8, 20))

        assert sum(p.income for p in outlook) == 0

    def test_급여일이_남았으면_그_날에_들어온다(self) -> None:
        snapshot = _snapshot(income_day=25)
        outlook = month_outlook(snapshot, today=date(2026, 8, 20))

        assert [p.income for p in outlook if p.day == 25] == [2_900_000]

    def test_마지막_날에는_남은_날이_없다(self) -> None:
        snapshot = _snapshot()
        outlook = month_outlook(snapshot, today=date(2026, 8, 31))

        assert [p.day for p in outlook] == [31]
        assert outlook[0].balance == snapshot.account_balance

    def test_회차가_끝난_확정지출은_빠지지_않는다(self) -> None:
        snapshot = _snapshot(
            fixed_expenses=[
                FixedExpense(
                    label="끝난 할부",
                    amount=100_000,
                    charge_day=25,
                    expense_type=ExpenseType.INSTALLMENT,
                    remaining_months=0,
                )
            ]
        )
        outlook = month_outlook(snapshot, today=date(2026, 8, 20))

        assert all(p.fixed_outflow == 0 for p in outlook)
