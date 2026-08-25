"""카드 혜택 판정 — 순수 계산.

DB·LLM 어느 쪽도 모른다. src/repository/card.py 가 가져온 원본 행(리스트)과
숫자만 받아 계산하므로 라이브 DB 없이 단위 테스트가 가능하다
(CLAUDE.md "엔진은 LLM을 모른다" / 배치·런타임 분리 원칙과 같은 이유).

규칙 적용 우선순위(backend/README.md)를 그대로 구현한다.
    1) 결제 카테고리와 정확히 일치하는 검수 완료 규칙이 있으면 그것을 적용
    2) 없으면 ALL 규칙을 폴백으로 적용
    3) 둘 다 없으면 할인 없음
두 규칙을 합산하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_FLOOR, Decimal

from src.repository.card import BenefitRule, Exclusion

_PERFORMANCE_EXCLUSION_TYPES = ("PERFORMANCE", "BOTH")
_DISCOUNT_EXCLUSION_TYPES = ("DISCOUNT", "BOTH")


@dataclass(frozen=True, slots=True)
class ExclusionFlags:
    performance_excluded: bool
    discount_excluded: bool


def select_rule(
    rules: list[BenefitRule], perf: int, category: str
) -> BenefitRule | None:
    """실적 구간·카테고리에 맞는 검수 완료 규칙 하나를 고른다.

    verified=false 는 후보에서 아예 제외한다 — 검수 게이트를 여기서
    통과시키지 않으면 호출부마다 다시 필터링해야 하고, 하나라도
    빠뜨리면 미검수 규칙이 판정에 새어 들어간다.
    """
    candidates = [
        r
        for r in rules
        if r.verified
        and r.perf_min <= perf
        and (r.perf_max is None or perf < r.perf_max)
        and r.category in (category, "ALL")
    ]
    if not candidates:
        return None
    # 카테고리 전용 규칙을 ALL보다 먼저 오게 정렬해 하나만 취한다.
    # backend/README.md의 SQL 패턴(ORDER BY ... LIMIT 1)과 동일한 결과를 낸다.
    candidates.sort(key=lambda r: 0 if r.category == category else 1)
    return candidates[0]


def classify_exclusions(
    exclusions: list[Exclusion], category: str, payment_type: str
) -> ExclusionFlags:
    """실적 제외와 할인 제외를 구분해 판정한다.

    무이자 할부는 실적에 잡히지 않지만 할인은 적용되는 카드가 있으므로
    (schema.sql 주석) 두 플래그를 하나로 합치면 그 구분이 사라진다.
    verified=false 제외 행은 무시한다 — 검수 전 항목이 판정에 영향을 주면
    card_benefit_rule과 검수 기준이 어긋난다.
    """
    performance_excluded = False
    discount_excluded = False
    for e in exclusions:
        if not e.verified:
            continue
        matched = (e.target_kind == "CATEGORY" and e.target_value == category) or (
            e.target_kind == "PAYMENT_TYPE" and e.target_value == payment_type
        )
        if not matched:
            continue
        if e.exclusion_type in _PERFORMANCE_EXCLUSION_TYPES:
            performance_excluded = True
        if e.exclusion_type in _DISCOUNT_EXCLUSION_TYPES:
            discount_excluded = True
    return ExclusionFlags(performance_excluded, discount_excluded)


def raw_discount_amount(amount: int, discount_rate: Decimal) -> int:
    """할인율을 곱해 원 단위로 내림한다.

    한 원 미만 절상하면 화면에 표시된 예상 할인액보다 실제 청구서의
    할인이 적어 보이는 불일치가 생긴다. 카드사 정산은 보통 절사이므로
    내림을 기본으로 한다.
    """
    return int((Decimal(amount) * discount_rate).to_integral_value(rounding=ROUND_FLOOR))


def compute_discount(
    rule: BenefitRule | None,
    amount: int,
    discount_excluded: bool,
    monthly_cap: int | None,
) -> int:
    """단일 거래 기준 예상 할인액.

    category_cap·monthly_cap은 이번 한 건의 계산값에만 적용한다. 같은
    실적 기간 내 이전 거래들이 이미 한도를 얼마나 소진했는지는 반영하지
    않는다 — 그러려면 기간 내 전체 거래를 다시 순회하며 각 건의 할인을
    재계산해야 하는데, /api/route는 "아직 결제하지 않은 한 건"을 판정하는
    엔드포인트라 첫 구현 범위에서는 뺐다. 실제 잔여 한도 추적이 필요해지면
    이 함수의 시그니처에 기존 소진액을 인자로 추가해야 한다.
    """
    if rule is None or discount_excluded:
        return 0
    discount = raw_discount_amount(amount, rule.discount_rate)
    if rule.category_cap is not None:
        discount = min(discount, rule.category_cap)
    if monthly_cap is not None:
        discount = min(discount, monthly_cap)
    return discount


def minimum_qualifying_perf(rules: list[BenefitRule], category: str) -> int | None:
    """이 카테고리로 어떤 할인이든 받기 위한 최소 실적 문턱.

    카드 A처럼 구간이 여럿이어도 가장 낮은 구간의 perf_min이 문턱이다.
    지금 perf_current가 상위 구간에 있는지는 discount 계산(select_rule)이
    이미 반영하므로, 여기서는 "0원도 할인 못 받는 상태"를 벗어나는
    기준만 구한다.
    """
    matching = [
        r.perf_min for r in rules if r.verified and r.category in (category, "ALL")
    ]
    return min(matching) if matching else None


def month_start_period(as_of: date) -> tuple[date, date]:
    """전월 1일 ~ 전월 말일. perf_period_type=MONTH_START 카드에 쓴다."""
    first_of_this_month = as_of.replace(day=1)
    last_month_end = first_of_this_month - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    return last_month_start, last_month_end


# 청구 마감일-결제일 간격의 기본값. schema.sql은 card.billing_close_day(카드 단위
# 고정값)만 두고 persona_card.payment_day(페르소나별 결제일)와 잇는 컬럼이 없다.
# 국내 카드에서 가장 흔한 조합인 "14일 마감·25일 결제"(11일 간격)를 기본으로 쓴다 —
# 카드 B 시드값(billing_close_day=14)과 카드 A 페르소나 다수의 payment_day=25가
# 정확히 이 간격이라 시연 데이터와도 맞아떨어진다. 팀 확인 대기 중(다음할일.md).
DEFAULT_BILLING_OFFSET_DAYS = 11


def billing_cycle_period(
    payment_day: int, as_of: date, offset_days: int = DEFAULT_BILLING_OFFSET_DAYS
) -> tuple[date, date]:
    """결제일에서 마감일을 역산해, 가장 최근에 끝난 청구 주기를 반환한다.

    perf_period_type=BILLING_CYCLE 카드에 쓴다. 마감일은 card.billing_close_day의
    CHECK 제약(1~28)과 같은 범위로 맞춘다 — 29~31일은 월마다 존재 여부가 달라
    "마감일"이라는 고정 개념과 맞지 않는다.

    as_of가 이번 달 마감일보다 뒤면 이번 달 마감이 이미 끝난 주기이고,
    아직 마감일 전이면(당일 포함) 지난달 마감이 가장 최근에 끝난 주기다.
    """
    close_day = ((payment_day - offset_days - 1) % 28) + 1

    def _close_date(year: int, month: int) -> date:
        return date(year, month, close_day)

    this_month_close = _close_date(as_of.year, as_of.month)
    if as_of > this_month_close:
        period_end = this_month_close
    else:
        prev_year, prev_month = (
            (as_of.year, as_of.month - 1)
            if as_of.month > 1
            else (as_of.year - 1, 12)
        )
        period_end = _close_date(prev_year, prev_month)

    start_year, start_month = (
        (period_end.year, period_end.month - 1)
        if period_end.month > 1
        else (period_end.year - 1, 12)
    )
    period_start = _close_date(start_year, start_month) + timedelta(days=1)

    return period_start, period_end


def performance_period(
    perf_period_type: str, as_of: date, payment_day: int | None = None
) -> tuple[date, date]:
    """card.perf_period_type에 따라 실적 산정 기간을 고른다."""
    if perf_period_type == "MONTH_START":
        return month_start_period(as_of)
    if perf_period_type == "BILLING_CYCLE":
        if payment_day is None:
            raise ValueError("BILLING_CYCLE 카드는 payment_day가 있어야 합니다")
        return billing_cycle_period(payment_day, as_of)
    raise ValueError(f"알 수 없는 실적 산정 방식: {perf_period_type}")
