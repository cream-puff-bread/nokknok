"""엔진 규칙 판정 단위 테스트 — DB 없이 실행된다.

backend/README.md "엔진 필수 단위 테스트" 표의 케이스를 구현보다 먼저
작성한다. 숫자는 data/cards.seed.sql의 카드 A/B/C 시드 값과 정확히
일치시킨다 — 시드가 바뀌면 이 테스트도 함께 갱신해야 한다.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from src.engine.qualification import (
    billing_cycle_period,
    classify_exclusions,
    compute_discount,
    minimum_qualifying_perf,
    month_start_period,
    performance_period,
    select_rule,
)
from src.repository.card import BenefitRule, Exclusion

# ─────────────────────────────────────────────
# data/cards.seed.sql 그대로 옮긴 고정값
# ─────────────────────────────────────────────
CARD_A_RULES = [
    BenefitRule(1, 1, 300_000, 500_000, "DINING", Decimal("0.0500"), 10_000, 2, True),
    BenefitRule(2, 1, 300_000, 500_000, "ONLINE", Decimal("0.0300"), 8_000, 2, True),
    BenefitRule(3, 1, 300_000, 500_000, "TRANSPORT", Decimal("0.0500"), 5_000, 2, True),
    BenefitRule(4, 1, 500_000, 1_000_000, "DINING", Decimal("0.0700"), 20_000, 2, True),
    BenefitRule(5, 1, 500_000, 1_000_000, "ONLINE", Decimal("0.0500"), 15_000, 2, True),
    BenefitRule(6, 1, 500_000, 1_000_000, "TRANSPORT", Decimal("0.0700"), 10_000, 2, True),
    BenefitRule(7, 1, 1_000_000, None, "DINING", Decimal("0.1000"), 30_000, 2, True),
    BenefitRule(8, 1, 1_000_000, None, "ONLINE", Decimal("0.0700"), 20_000, 2, True),
    BenefitRule(9, 1, 1_000_000, None, "TRANSPORT", Decimal("0.1000"), 15_000, 2, True),
]
CARD_A_EXCLUSIONS = [
    Exclusion(1, 1, "BOTH", "PAYMENT_TYPE", "INTEREST_FREE", 4, True),
    Exclusion(2, 1, "PERFORMANCE", "CATEGORY", "TAX", 4, True),
]

CARD_B_RULES = [
    BenefitRule(10, 2, 400_000, None, "ALL", Decimal("0.0200"), 30_000, 6, True),
]
CARD_B_EXCLUSIONS = [
    Exclusion(3, 2, "BOTH", "PAYMENT_TYPE", "INTEREST_FREE", 7, True),
    Exclusion(4, 2, "BOTH", "CATEGORY", "GIFT_CARD", 7, True),
]

CARD_C_RULES = [
    BenefitRule(11, 3, 300_000, None, "ONLINE", Decimal("0.1000"), 20_000, 9, True),
    BenefitRule(12, 3, 300_000, None, "DELIVERY", Decimal("0.1500"), 10_000, 9, True),
    BenefitRule(13, 3, 300_000, None, "CAFE", Decimal("0.1000"), 10_000, 9, True),
    BenefitRule(14, 3, 300_000, None, "ALL", Decimal("0.0100"), 5_000, 10, True),
]
CARD_C_EXCLUSIONS = [
    Exclusion(5, 3, "PERFORMANCE", "CATEGORY", "TAX", 11, True),
    Exclusion(6, 3, "PERFORMANCE", "CATEGORY", "UTILITY", 11, True),
    Exclusion(7, 3, "PERFORMANCE", "CATEGORY", "GIFT_CARD", 11, True),
    Exclusion(8, 3, "PERFORMANCE", "CATEGORY", "INSURANCE", 11, True),
    Exclusion(9, 3, "PERFORMANCE", "CATEGORY", "EDUCATION", 11, True),
    Exclusion(10, 3, "PERFORMANCE", "PAYMENT_TYPE", "INTEREST_FREE", 11, True),
    Exclusion(11, 3, "DISCOUNT", "CATEGORY", "TRANSPORT", 12, True),
]


def _rate(rule: BenefitRule) -> str:
    return str(rule.discount_rate)


class TestSelectRule:
    def test_카드_C_온라인_결제는_10퍼센트다_ALL과_합산되지_않는다(self):
        rule = select_rule(CARD_C_RULES, perf=300_000, category="ONLINE")

        assert rule is not None
        assert rule.category == "ONLINE"
        assert _rate(rule) == "0.1000"

    def test_카드_C_교통_결제는_ALL이_매치된다(self):
        # TRANSPORT 전용 규칙이 없으므로 ALL(1%)로 폴백한다.
        # 할인 제외 여부는 classify_exclusions가 별도로 판단한다.
        rule = select_rule(CARD_C_RULES, perf=300_000, category="TRANSPORT")

        assert rule is not None
        assert rule.category == "ALL"
        assert _rate(rule) == "0.0100"

    def test_카드_A_실적_구간_경계에서_적용율이_바뀐다(self):
        below = select_rule(CARD_A_RULES, perf=499_999, category="ONLINE")
        at_boundary = select_rule(CARD_A_RULES, perf=500_000, category="ONLINE")

        assert below is not None and _rate(below) == "0.0300"
        assert at_boundary is not None and _rate(at_boundary) == "0.0500"

    def test_해당하는_규칙이_없으면_None이다(self):
        # 카드 A는 ALL 폴백 규칙 자체가 없다.
        assert select_rule(CARD_A_RULES, perf=500_000, category="GROCERY") is None


class TestClassifyExclusions:
    def test_카드_C_세금은_실적에서만_제외되고_할인대상은_아니다(self):
        flags = classify_exclusions(CARD_C_EXCLUSIONS, category="TAX", payment_type="LUMP")

        assert flags.performance_excluded is True
        assert flags.discount_excluded is False

    def test_카드_C_교통은_할인에서만_제외되고_실적에는_반영된다(self):
        flags = classify_exclusions(
            CARD_C_EXCLUSIONS, category="TRANSPORT", payment_type="LUMP"
        )

        assert flags.performance_excluded is False
        assert flags.discount_excluded is True

    def test_카드_A_무이자_할부는_실적과_할인_모두_제외된다(self):
        # BOTH + PAYMENT_TYPE이므로 카테고리와 무관하게 걸린다.
        flags = classify_exclusions(
            CARD_A_EXCLUSIONS, category="DINING", payment_type="INTEREST_FREE"
        )

        assert flags.performance_excluded is True
        assert flags.discount_excluded is True

    def test_미검수_제외항목은_무시한다(self):
        unverified = [Exclusion(99, 1, "BOTH", "CATEGORY", "DINING", None, False)]
        flags = classify_exclusions(unverified, category="DINING", payment_type="LUMP")

        assert flags.performance_excluded is False
        assert flags.discount_excluded is False


class TestComputeDiscount:
    def test_카테고리_한도를_초과하면_잘린다(self):
        rule = CARD_A_RULES[1]  # ONLINE 3%, category_cap 8,000원
        # monthly_cap을 None으로 넘겨 category_cap만 단독으로 검증한다.
        discount = compute_discount(
            rule, amount=1_000_000, discount_excluded=False, monthly_cap=None
        )

        assert discount == 8_000  # 30,000원이 아니라 한도 8,000원

    def test_월_통합_한도를_초과하면_잘린다(self):
        rule = BenefitRule(
            99, 1, 1_000_000, None, "DINING", Decimal("0.1000"), None, None, True
        )
        # category_cap을 None으로 두어 monthly_cap만 단독으로 검증한다.
        discount = compute_discount(
            rule, amount=1_000_000, discount_excluded=False, monthly_cap=50_000
        )

        assert discount == 50_000  # 100,000원이 아니라 카드 A의 월 한도 50,000원

    def test_할인_제외면_규칙이_있어도_0원이다(self):
        rule = CARD_C_RULES[0]
        discount = compute_discount(
            rule, amount=1_000_000, discount_excluded=True, monthly_cap=None
        )

        assert discount == 0

    def test_매치된_규칙이_없으면_0원이다(self):
        discount = compute_discount(
            None, amount=1_000_000, discount_excluded=False, monthly_cap=None
        )

        assert discount == 0


class TestMinimumQualifyingPerf:
    def test_카드_A_외식은_30만원부터다(self):
        assert minimum_qualifying_perf(CARD_A_RULES, "DINING") == 300_000

    def test_카드_B는_ALL만_있어_카테고리와_무관하게_40만원이다(self):
        assert minimum_qualifying_perf(CARD_B_RULES, "DINING") == 400_000

    def test_매치되는_규칙이_전혀_없으면_None이다(self):
        assert minimum_qualifying_perf(CARD_A_RULES, "GROCERY") is None


class TestMonthStartPeriod:
    def test_전월_1일부터_말일까지를_반환한다(self):
        start, end = month_start_period(date(2026, 9, 5))

        assert start == date(2026, 8, 1)
        assert end == date(2026, 8, 31)

    def test_1월_기준이면_전년_12월이다(self):
        start, end = month_start_period(date(2026, 1, 15))

        assert start == date(2025, 12, 1)
        assert end == date(2025, 12, 31)


class TestBillingCyclePeriod:
    """카드 B(BILLING_CYCLE): 결제일이 바뀌면 마감일도 바뀌어 실적 집계 기간이
    달라진다는 게 backend/README.md 필수 테스트다.

    offset_days는 이제 card.billing_offset_days에서 온 실제 값을 받는
    파라미터다(기본값 없음) — 2026-08-27 카드 B 실측 검증(VANDAL·빵빵덕 논의)
    으로 모든 카드에 같은 오프셋을 임의 적용하던 이전 방식(고정 상수 11)이
    페르소나 실적 판정을 실제로 뒤집는다는 게 드러나 폐기됐다.
    """

    def test_결제일이_다르면_같은_카드라도_집계_기간이_달라진다(self):
        as_of = date(2026, 9, 20)

        period_25 = billing_cycle_period(payment_day=25, as_of=as_of, offset_days=11)
        period_14 = billing_cycle_period(payment_day=14, as_of=as_of, offset_days=11)

        assert period_25 != period_14

    def test_카드_B_시드값(self):
        # 카드 B 실제 값: payment_day=14, billing_offset_days=14
        # (2026-08-27 VANDAL·빵빵덕 합의 — 마감일 28일, 기간 실측으로 검증됨).
        start, end = billing_cycle_period(payment_day=14, as_of=date(2026, 9, 20), offset_days=14)

        assert end == date(2026, 8, 28)
        assert start == date(2026, 7, 29)

    def test_마감일_당일에는_아직_그_주기가_끝나지_않은_것으로_본다(self):
        start, end = billing_cycle_period(payment_day=25, as_of=date(2026, 9, 14), offset_days=11)

        assert end == date(2026, 8, 14)
        assert start == date(2026, 7, 15)

    def test_performance_period가_BILLING_CYCLE을_위임한다(self):
        via_wrapper = performance_period(
            "BILLING_CYCLE", as_of=date(2026, 9, 20), payment_day=14, billing_offset_days=14
        )
        direct = billing_cycle_period(payment_day=14, as_of=date(2026, 9, 20), offset_days=14)

        assert via_wrapper == direct

    def test_BILLING_CYCLE인데_payment_day가_없으면_에러(self):
        with pytest.raises(ValueError, match="payment_day"):
            performance_period("BILLING_CYCLE", as_of=date(2026, 9, 20), billing_offset_days=14)

    def test_BILLING_CYCLE인데_billing_offset_days가_없으면_에러(self):
        with pytest.raises(ValueError, match="billing_offset_days"):
            performance_period("BILLING_CYCLE", as_of=date(2026, 9, 20), payment_day=14)

    def test_MONTH_START은_month_start_period와_동일하다(self):
        as_of = date(2026, 9, 20)
        assert performance_period("MONTH_START", as_of) == month_start_period(as_of)
