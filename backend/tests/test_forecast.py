"""변동 지출 예측과 잔고 추이 테스트.

DB도 네트워크도 쓰지 않는다. 예측 모듈은 입력이 같으면 항상 같은 결과를
내야 하므로 today 를 인자로 고정해 검증한다.
"""

from __future__ import annotations

from datetime import date

import pytest

from src.adapter.base import (
    ExpenseType,
    FinancialSnapshot,
    FixedExpense,
    PaymentType,
    Transaction,
)
from src.forecast import (
    PlannedPurchase,
    PurchasePaymentType,
    ScenarioLevel,
    forecast_cashflow,
    forecast_variable_spend,
)

TODAY = date(2026, 5, 10)


def txn(
    day: date,
    amount: int,
    category: str = "DINING",
    *,
    recurring: bool = False,
    payment_type: PaymentType = PaymentType.LUMP,
    installment_months: int = 0,
) -> Transaction:
    return Transaction(
        txn_date=day,
        merchant="가맹점",
        amount=amount,
        category=category,
        payment_type=payment_type,
        card_id=1,
        installment_months=installment_months,
        is_recurring=recurring,
    )


def snapshot(**kwargs) -> FinancialSnapshot:
    base = {
        "account_balance": 1_000_000,
        "monthly_income": 0,
        "income_day": 25,
        "transactions": [],
        "fixed_expenses": [],
    }
    return FinancialSnapshot(**{**base, **kwargs})


# ─────────────────────────────────────────────
# 표본 구성
# ─────────────────────────────────────────────
class Test표본:
    def test_완결되지_않은_당월은_표본에서_뺀다(self):
        """오늘이 5월 10일이면 5월은 열흘치뿐이라 다른 달보다 작다.

        그대로 넣으면 모든 카테고리 예측이 아래로 끌린다.
        """
        rows = [txn(date(2026, m, 5), 100_000) for m in (2, 3, 4)]
        rows.append(txn(date(2026, 5, 5), 10_000))

        result = forecast_variable_spend(rows, today=TODAY)

        assert result.months_used == 3
        assert result.txn_count == 3
        assert result.by_level[ScenarioLevel.NORMAL] == 100_000

    def test_정기결제도_표본에_넣는다(self):
        """시드에서 is_recurring 거래는 통신요금뿐이고 fixed_expense 에 통신
        항목이 없다. 빼면 페르소나마다 월 5만원가량이 예측에서 사라진다.

        FileProvider 는 fixed_expenses=[] 를 반환하므로 업로드 경로에서는
        정기 지출 전부가 사라진다. 정기 결제는 규칙적이라 중앙값·이동평균이
        오히려 잘 다룬다.
        """
        rows = [txn(date(2026, m, 5), 100_000) for m in (2, 3, 4)]
        rows += [txn(date(2026, m, 6), 50_000, recurring=True) for m in (2, 3, 4)]

        result = forecast_variable_spend(rows, today=TODAY)

        assert result.by_level[ScenarioLevel.NORMAL] == 150_000

    def test_할부_거래는_표본에서_뺀다(self):
        """구매가 전액이 한 달에 잡히면 그 달 총액이 왜곡된다.

        남은 회차는 사라지지 않는다. projection 이 확정 지출로 따로 더한다.
        """
        rows = [txn(date(2026, m, 5), 100_000) for m in (2, 3, 4)]
        rows.append(
            txn(
                date(2026, 3, 9),
                1_200_000,
                payment_type=PaymentType.INSTALLMENT,
                installment_months=12,
            )
        )

        result = forecast_variable_spend(rows, today=TODAY)

        assert result.by_level[ScenarioLevel.NORMAL] == 100_000

    def test_표본이_없어도_예외를_던지지_않는다(self):
        """숫자를 못 내는 것과 근거가 얇은 것은 다르다."""
        result = forecast_variable_spend([], today=TODAY)

        assert result.months_used == 0
        assert result.cold_start is True
        assert all(v == 0 for v in result.by_level.values())


# ─────────────────────────────────────────────
# 점 추정과 밴드
# ─────────────────────────────────────────────
class Test예측:
    def test_관측이_없는_달은_0으로_채운다(self):
        """그 달에 안 썼다는 것도 소비 패턴이다. 빼고 평균 내면 높게 나온다."""
        rows = [
            txn(date(2026, 2, 5), 90_000, "MEDICAL"),
            txn(date(2026, 3, 5), 0 + 30_000, "MEDICAL"),
        ]
        rows += [txn(date(2026, m, 5), 10_000, "DINING") for m in (2, 3, 4)]

        result = forecast_variable_spend(rows, today=TODAY)

        # MEDICAL 은 4월 관측이 없다. 중앙값 30,000 / 최근3개월 평균 40,000
        assert result.by_category["MEDICAL"] == 35_000

    def test_밴드는_카테고리_합산이_아니라_총액에서_구한다(self):
        """카테고리별 분위수를 더하면 모든 카테고리가 같은 달에 동시에
        고점을 찍는다고 가정하는 것과 같아 밴드가 부풀려진다.

        여기서는 두 카테고리가 서로 반대로 움직여 총액이 매달 같다.
        총액 기준이면 변동이 없으므로 세 시나리오가 같아야 한다.
        카테고리별로 뽑아 더하면 여유·빠듯이 벌어져 이 테스트가 깨진다.
        """
        rows = []
        for month, (a, b) in zip((1, 2, 3, 4), ((100, 200), (200, 100), (100, 200), (200, 100))):
            rows.append(txn(date(2026, month, 5), a * 1000, "DINING"))
            rows.append(txn(date(2026, month, 6), b * 1000, "ONLINE"))

        result = forecast_variable_spend(rows, today=TODAY)

        assert result.by_level[ScenarioLevel.NORMAL] == 300_000
        assert result.by_level[ScenarioLevel.COMFORTABLE] == 300_000
        assert result.by_level[ScenarioLevel.TIGHT] == 300_000

    def test_빠듯이_여유보다_많이_쓴다(self):
        amounts = [100_000, 200_000, 150_000, 400_000]
        rows = [txn(date(2026, m, 5), a) for m, a in zip((1, 2, 3, 4), amounts)]

        result = forecast_variable_spend(rows, today=TODAY)

        assert (
            result.by_level[ScenarioLevel.COMFORTABLE]
            < result.by_level[ScenarioLevel.NORMAL]
            < result.by_level[ScenarioLevel.TIGHT]
        )

    @pytest.mark.parametrize(
        ("months", "expected_cold_start"),
        [(1, True), (2, True), (3, False), (4, False)],
    )
    def test_콜드스타트는_완결된_달_3개_미만이다(self, months, expected_cold_start):
        """월 단위 분위수를 뽑으려면 관측이 최소 셋은 있어야 한다.

        둘이면 q25·q75 가 두 점 사이 보간에 불과해 밴드가 표본 범위 그대로다.
        """
        rows = [txn(date(2026, m, 5), 100_000) for m in range(1, months + 1)]

        result = forecast_variable_spend(rows, today=TODAY)

        assert result.months_used == months
        assert result.cold_start is expected_cold_start


# ─────────────────────────────────────────────
# 잔고 추이
# ─────────────────────────────────────────────
def fixed(amount: int, charge_day: int, remaining_months: int | None = None) -> FixedExpense:
    return FixedExpense(
        expense_type=ExpenseType.SUBSCRIPTION,
        label="고정비",
        amount=amount,
        charge_day=charge_day,
        remaining_months=remaining_months,
    )


class Test잔고추이:
    def test_첫_점이_이번_달이고_개월_수만큼_나온다(self):
        result = forecast_cashflow(snapshot(), today=TODAY, months=6)

        for scenario in result.scenarios:
            assert len(scenario.points) == 6
            assert scenario.points[0].month == "2026-05"
            assert scenario.points[-1].month == "2026-10"

    def test_이번_달_청구일이_지난_확정지출은_이번_달에_빠지지_않는다(self):
        """오늘이 10일인데 5일에 이미 빠져나갔다면 account_balance 에 반영돼 있다."""
        snap = snapshot(fixed_expenses=[fixed(100_000, charge_day=5)])

        points = forecast_cashflow(snap, today=TODAY, months=3).scenarios[0].points

        assert points[0].balance == 1_000_000
        assert points[1].balance == 900_000

    def test_할부가_끝나면_그_달부터_확정지출에서_빠진다(self):
        """이 감소를 반영하지 않으면 할부가 겹친 이용자의 회복 시점이 사라진다."""
        snap = snapshot(fixed_expenses=[fixed(100_000, charge_day=20, remaining_months=2)])

        points = forecast_cashflow(snap, today=TODAY, months=4).scenarios[0].points

        assert points[0].balance == 900_000
        assert points[1].balance == 800_000
        # 남은 청구가 끝났으므로 이후로는 잔고가 그대로다.
        assert points[2].balance == 800_000
        assert points[3].balance == 800_000

    def test_급여일이_지났으면_이번_달_급여를_더하지_않는다(self):
        """이미 들어온 돈은 account_balance 에 포함돼 있다."""
        received = snapshot(monthly_income=3_000_000, income_day=5)
        upcoming = snapshot(monthly_income=3_000_000, income_day=25)

        assert forecast_cashflow(received, today=TODAY, months=1).scenarios[0].points[0].balance == 1_000_000
        assert forecast_cashflow(upcoming, today=TODAY, months=1).scenarios[0].points[0].balance == 4_000_000

    def test_이번_달_변동지출은_남은_일수만큼만_센다(self):
        """5월 10일이면 31일 중 21일이 남았다."""
        rows = [txn(date(2026, m, 5), 310_000) for m in (2, 3, 4)]
        snap = snapshot(transactions=rows)

        points = forecast_cashflow(snap, today=TODAY, months=2).scenarios[1].points

        assert points[0].balance == 1_000_000 - round(310_000 * 21 / 31)
        assert points[1].balance == points[0].balance - 310_000


class Test검토중인지출:
    def test_일시불은_첫_달에_전액_빠진다(self):
        purchase = PlannedPurchase(amount=1_800_000)

        points = forecast_cashflow(snapshot(), today=TODAY, months=3, purchase=purchase).scenarios[0].points

        assert points[0].balance == 1_000_000 - 1_800_000
        assert points[1].balance == points[0].balance

    def test_할부_청구_총액이_원금과_같다(self):
        """나머지를 버리면 청구 총액이 원금보다 적어져 할부가 유리해 보인다."""
        purchase = PlannedPurchase(
            amount=1_000_000,
            payment_type=PurchasePaymentType.INSTALLMENT,
            installment_months=3,
        )

        points = forecast_cashflow(snapshot(), today=TODAY, months=6, purchase=purchase).scenarios[0].points

        assert points[2].balance == 1_000_000 - 1_000_000
        assert points[5].balance == points[2].balance

    def test_할부_개월이_예측_기간보다_길어도_동작한다(self):
        purchase = PlannedPurchase(
            amount=1_200_000,
            payment_type=PurchasePaymentType.INTEREST_FREE,
            installment_months=24,
        )

        points = forecast_cashflow(snapshot(), today=TODAY, months=6, purchase=purchase).scenarios[0].points

        assert points[5].balance == 1_000_000 - 50_000 * 6

    def test_일시불에_할부_개월을_주면_거부한다(self):
        with pytest.raises(ValueError):
            PlannedPurchase(amount=100, installment_months=3)


class Test적자전환:
    def test_적자로_가지_않으면_None이다(self):
        assert forecast_cashflow(snapshot(), today=TODAY, months=6).dead_point is None

    def test_같은_달에_여럿이_음수면_부족액이_큰_쪽을_보여준다(self):
        """화면에는 하나만 표시한다. 덜 나쁜 쪽을 보여주면 위험을 축소해 전달하게 된다."""
        amounts = [400_000, 800_000, 600_000, 1_600_000]
        rows = [txn(date(2026, m, 5), a) for m, a in zip((1, 2, 3, 4), amounts)]
        snap = snapshot(account_balance=300_000, transactions=rows)

        result = forecast_cashflow(snap, today=TODAY, months=6)

        assert result.dead_point is not None
        earliest = result.dead_point.month
        negatives = {
            s.level: -p.balance
            for s in result.scenarios
            for p in s.points
            if p.month == earliest and p.balance < 0
        }
        assert result.dead_point.shortage == max(negatives.values())
        assert negatives[result.dead_point.level] == result.dead_point.shortage

    def test_콜드스타트_여부가_결과에_함께_실린다(self):
        rows = [txn(date(2026, 4, 5), 100_000)]

        meta = forecast_cashflow(snapshot(transactions=rows), today=TODAY).meta

        assert meta.months_used == 1
        assert meta.txn_count == 1
        assert meta.cold_start is True


class Test기존할부:
    """이미 결제한 할부의 남은 회차.

    금액과 날짜가 이미 정해져 있어 예측 대상이 아니라 계산 대상이다.
    시드에서 persona 1 의 386,300원 6개월 할부는 거래로만 존재하고
    fixed_expense 에는 없다 — 반영하지 않으면 통째로 누락된다.
    """

    def installment(self, day: date, amount: int, months: int) -> Transaction:
        return txn(
            day,
            amount,
            "ONLINE",
            payment_type=PaymentType.INSTALLMENT,
            installment_months=months,
        )

    def test_남은_회차만_앞으로_빠져나간다(self):
        # 3월 15일에 60,000원 6개월 할부. 오늘은 5월 10일이므로 3·4월분은 지났고
        # 5월부터 8월까지 네 회차가 남는다.
        rows = [self.installment(date(2026, 3, 15), 60_000, 6)]

        points = forecast_cashflow(
            snapshot(transactions=rows), today=TODAY, months=6
        ).scenarios[1].points

        drops = [1_000_000 - points[0].balance] + [
            points[i - 1].balance - points[i].balance for i in range(1, 6)
        ]
        assert drops[:4] == [10_000, 10_000, 10_000, 10_000]
        assert drops[4:] == [0, 0]

    def test_이미_지난_이번_달_청구는_다시_빼지_않는다(self):
        """청구일이 오늘보다 앞이면 그 돈은 account_balance 에 반영돼 있다."""
        rows = [self.installment(date(2026, 5, 3), 60_000, 6)]

        points = forecast_cashflow(
            snapshot(transactions=rows), today=TODAY, months=2
        ).scenarios[1].points

        assert points[0].balance == 1_000_000
        assert points[1].balance == 990_000

    def test_마지막_회차가_나머지를_흡수한다(self):
        """나눗셈에서 버리면 청구 총액이 원금보다 적어진다."""
        rows = [self.installment(date(2026, 5, 20), 100_000, 3)]

        points = forecast_cashflow(
            snapshot(transactions=rows), today=TODAY, months=4
        ).scenarios[1].points

        assert points[2].balance == 1_000_000 - 100_000
        assert points[3].balance == points[2].balance

    def test_예측_기간_밖의_회차는_무시한다(self):
        rows = [self.installment(date(2026, 1, 20), 240_000, 24)]

        points = forecast_cashflow(
            snapshot(transactions=rows), today=TODAY, months=3
        ).scenarios[1].points

        assert 1_000_000 - points[2].balance == 10_000 * 3
