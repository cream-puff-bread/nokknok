"""변동 지출 예측.

확정 지출(구독·할부·대출)은 금액과 날짜가 이미 정해져 있으므로 예측 대상이
아니다. 여기서 다루는 것은 나머지 — 외식, 장보기, 온라인 쇼핑처럼 달마다
달라지는 지출뿐이다.

## 표본에서 빼는 것

1. **완결되지 않은 달** — 오늘이 8월 24일이면 8월 표본은 20일치뿐이라
   다른 달보다 작다. 그대로 넣으면 모든 카테고리 예측이 아래로 끌린다.
   실제 시연 데이터에서 8월 총액이 다른 달의 60% 수준이었다.
2. **정기 결제(is_recurring)** — fixed_expense 에 이미 잡혀 있다. 양쪽에
   넣으면 같은 돈을 두 번 뺀다.
3. **할부 거래** — 거래 금액은 구매가 전액이지만 현금 흐름은 여러 달에
   나뉜다. 월 청구액은 fixed_expense 의 INSTALLMENT 행이 갖고 있다.

## 점 추정과 밴드를 다르게 계산하는 이유

점 추정(보통 시나리오)은 카테고리별로 낸다. 카테고리마다 변동 폭이 달라서
한 덩어리로 다루면 외식의 안정성과 온라인 쇼핑의 널뜀이 섞여버린다.

밴드(여유·빠듯)는 **총액 표본**에서 뽑는다. 카테고리별 분위수를 더하면
모든 카테고리가 같은 달에 동시에 고점을 찍는다고 가정하는 것과 같아 밴드가
크게 부풀려진다. 시연 데이터로 재보면 (q75-q25)/q50 이 총액 기준 0.13~0.18
인데 카테고리 합산 기준으로는 0.26~0.53 으로 2~3배가 됐다. 실제로는 한 달에
모든 카테고리가 함께 튀지 않으므로 후자는 과장이다.

그래서 카테고리별 점 추정을 합산해 기준값을 만들고, 총액 표본에서 구한
비율(q25/q50, q75/q50)을 그 기준값에 곱한다.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from src.adapter.base import PaymentType, Transaction
from src.common.logging import get_logger
from src.forecast.models import ScenarioLevel

logger = get_logger(__name__)

# 월 단위 분위수를 뽑으려면 관측이 최소 세 개는 있어야 한다. 두 개면
# q25·q75 가 두 점 사이 보간에 불과해 밴드가 표본 범위 그대로가 되고,
# 중앙값도 이동평균과 구분되지 않는다.
MIN_MONTHS_FOR_QUANTILES = 3

# 표본이 부족할 때 쓰는 밴드 비율.
# 시연 데이터 3인의 완결된 5개월 표본에서 총액 기준으로 측정한 값
# (q25/q50 0.90~0.99, q75/q50 1.06~1.15)의 가운데를 택했다.
# 표본이 세 명뿐이라 근거가 두텁지 않다. 실데이터가 쌓이면 다시 측정한다.
COLD_START_LOW_RATIO = 0.95
COLD_START_HIGH_RATIO = 1.10

# 이동평균에 쓸 최근 개월 수. 중앙값은 표본 전체를 보므로, 셋으로 잡으면
# 최근 추세에 가중을 주면서도 오래된 달을 버리지 않는다.
RECENT_MONTHS = 3


@dataclass(frozen=True, slots=True)
class VariableSpendForecast:
    """시나리오별 월 변동 지출 예측액과 그 근거."""

    by_level: dict[ScenarioLevel, int]
    by_category: dict[str, int]
    months_used: int
    txn_count: int

    @property
    def cold_start(self) -> bool:
        return self.months_used < MIN_MONTHS_FOR_QUANTILES


def _month_key(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def _is_variable(txn: Transaction) -> bool:
    """확정 지출과 겹치지 않는 거래만 남긴다."""
    if txn.is_recurring:
        return False
    return txn.payment_type is PaymentType.LUMP


def _monthly_totals_by_category(
    transactions: Iterable[Transaction], *, cutoff_month: str
) -> dict[str, dict[str, int]]:
    """카테고리 -> {월: 합계}. cutoff_month 이후(당월 포함)는 제외한다."""
    totals: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for txn in transactions:
        if not _is_variable(txn):
            continue
        month = _month_key(txn.txn_date)
        if month >= cutoff_month:
            continue
        totals[txn.category][month] += txn.amount
    return {cat: dict(months) for cat, months in totals.items()}


def _point_estimate(monthly: dict[str, int], all_months: list[str]) -> float:
    """카테고리 하나의 월 예상 지출.

    관측이 없는 달은 0 으로 채운다. 어떤 달에 그 카테고리를 아예 쓰지
    않았다면 그것도 실제 소비 패턴이라, 빼고 평균 내면 실제보다 높게 나온다.

    이동평균과 중앙값을 같은 비중으로 섞는다. 이동평균만 쓰면 지난달의
    일회성 대형 지출을 다음 달에도 쓸 것처럼 따라가고, 중앙값만 쓰면
    최근에 늘어난 추세를 반영하지 못한다. 두 실패 모드 중 어느 쪽으로도
    치우치지 않게 한다.
    """
    series = [monthly.get(month, 0) for month in all_months]
    if not series:
        return 0.0

    recent = series[-RECENT_MONTHS:]
    moving_average = statistics.fmean(recent)
    median = statistics.median(series)
    return (moving_average + median) / 2


def _band_ratios(total_by_month: list[int]) -> tuple[float, float]:
    """총액 표본에서 (여유 비율, 빠듯 비율)을 구한다."""
    if len(total_by_month) < MIN_MONTHS_FOR_QUANTILES:
        return COLD_START_LOW_RATIO, COLD_START_HIGH_RATIO

    q25, q50, q75 = statistics.quantiles(total_by_month, n=4, method="inclusive")
    if q50 <= 0:
        return COLD_START_LOW_RATIO, COLD_START_HIGH_RATIO
    return q25 / q50, q75 / q50


def forecast_variable_spend(
    transactions: Iterable[Transaction], *, today: date
) -> VariableSpendForecast:
    """월 변동 지출을 시나리오 세 가지로 예측한다.

    표본이 전혀 없어도 예외를 던지지 않는다. 0 원으로 예측하고 months_used=0
    으로 알린다 — 숫자를 못 내는 것과 근거가 얇은 것은 다르고, 화면은
    후자를 표시할 수 있어야 한다.
    """
    transactions = list(transactions)
    cutoff = _month_key(today)

    by_category_months = _monthly_totals_by_category(transactions, cutoff_month=cutoff)
    months = sorted({m for months in by_category_months.values() for m in months})

    txn_count = sum(
        1
        for t in transactions
        if _is_variable(t) and _month_key(t.txn_date) < cutoff
    )

    if not months:
        logger.info("변동 지출 표본 없음 — 0원으로 예측한다")
        return VariableSpendForecast(
            by_level=dict.fromkeys(ScenarioLevel, 0),
            by_category={},
            months_used=0,
            txn_count=txn_count,
        )

    by_category = {
        category: round(_point_estimate(monthly, months))
        for category, monthly in by_category_months.items()
    }
    normal = sum(by_category.values())

    total_by_month = [
        sum(monthly.get(month, 0) for monthly in by_category_months.values())
        for month in months
    ]
    low_ratio, high_ratio = _band_ratios(total_by_month)

    logger.info(
        "변동 지출 예측 개월=%d 카테고리=%d 밴드=%.3f~%.3f",
        len(months),
        len(by_category),
        low_ratio,
        high_ratio,
    )

    return VariableSpendForecast(
        by_level={
            ScenarioLevel.COMFORTABLE: round(normal * low_ratio),
            ScenarioLevel.NORMAL: normal,
            ScenarioLevel.TIGHT: round(normal * high_ratio),
        },
        by_category=by_category,
        months_used=len(months),
        txn_count=txn_count,
    )
