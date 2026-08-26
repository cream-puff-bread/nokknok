"""실제 시드 데이터로 예측 모듈을 검증한다.

단위 테스트는 합성 데이터로 규칙을 고정하고, 여기서는 generate_persona.py 가
만든 6개월치 실데이터에 대해 결과가 말이 되는지 본다. today 를 고정해
언제 돌려도 같은 결과가 나오게 한다.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.orm import Session

from src.adapter.factory import SourceKind, build_provider
from src.forecast import ScenarioLevel, forecast_cashflow

pytestmark = pytest.mark.integration

# 시드 거래는 2026-03-01 ~ 2026-08-20 이다. 8월을 미완결로 만들려고
# 그 달 안의 날짜를 고정한다.
TODAY = date(2026, 8, 24)


@pytest.fixture
def snapshot(db_session: Session):
    return build_provider(SourceKind.MOCK, session=db_session).fetch("INSTALLMENT_HEAVY")


def test_미완결인_당월을_빼고_다섯_달을_쓴다(snapshot):
    """시드는 3~8월이지만 8월은 20일까지뿐이다.

    포함하면 그 달 총액이 다른 달의 60% 수준이라 모든 예측이 아래로 끌린다.
    """
    meta = forecast_cashflow(snapshot, today=TODAY).meta

    assert meta.months_used == 5
    assert meta.cold_start is False
    assert meta.txn_count > 100


def test_여유_시나리오의_잔고가_항상_더_높다(snapshot):
    """여유는 적게 쓰는 경우다. 순서가 뒤집히면 화면의 밴드가 교차한다."""
    scenarios = {s.level: s.points for s in forecast_cashflow(snapshot, today=TODAY).scenarios}

    for i in range(6):
        comfortable = scenarios[ScenarioLevel.COMFORTABLE][i].balance
        normal = scenarios[ScenarioLevel.NORMAL][i].balance
        tight = scenarios[ScenarioLevel.TIGHT][i].balance
        assert comfortable >= normal >= tight


def test_월_라벨이_연속한다(snapshot):
    points = forecast_cashflow(snapshot, today=TODAY).scenarios[0].points

    assert [p.month for p in points] == [
        "2026-08",
        "2026-09",
        "2026-10",
        "2026-11",
        "2026-12",
        "2027-01",
    ]


def test_할부가_끝나면_월_확정지출이_줄어든다(snapshot):
    """할부 누적형 페르소나는 태블릿 2개월·노트북 7개월이 남아 있다.

    remaining_months 를 무시하면 할부가 끝난 뒤에도 계속 빠져나가는 것으로
    계산되어, 이 서비스가 보여주려는 회복 시점이 통째로 사라진다.
    """
    tablet = next(e for e in snapshot.fixed_expenses if e.remaining_months == 2)
    points = forecast_cashflow(snapshot, today=TODAY).scenarios[1].points

    monthly_drop = [
        points[i - 1].balance - points[i].balance for i in range(1, len(points))
    ]
    # 태블릿 할부가 끝난 뒤의 월 감소폭이 그 이전보다 최소 할부금만큼 작다.
    assert min(monthly_drop) <= max(monthly_drop) - tablet.amount


def test_검토중인_지출이_잔고를_끌어내린다(snapshot):
    from src.forecast import PlannedPurchase, PurchasePaymentType

    without = forecast_cashflow(snapshot, today=TODAY).scenarios[1].points[-1].balance
    with_purchase = forecast_cashflow(
        snapshot,
        today=TODAY,
        purchase=PlannedPurchase(
            amount=1_800_000,
            payment_type=PurchasePaymentType.INSTALLMENT,
            installment_months=12,
        ),
    ).scenarios[1].points[-1].balance

    # 12개월 할부 중 6회차까지 청구된다.
    assert without - with_purchase == 1_800_000 // 12 * 6
