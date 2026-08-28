"""엔진 라우팅 오케스트레이션 단위 테스트 — DB 없이 실행된다.

qualification.py의 규칙 판정 자체는 test_engine_qualification.py가 이미
검증하므로, 여기서는 route.py가 맡는 조립 책임만 확인한다.
    - 카드별로 실적을 독립 집계하는지 (다른 카드 거래가 섞이지 않는지)
    - 실적 제외 거래가 실적 합계에서 실제로 빠지는지
    - 미검수 카드를 후보에서 빼고 개수를 세는지
    - 후보가 전부 사라지면 NoVerifiedRuleError를 던지는지
    - best/alternatives 랭킹이 예상 할인액 내림차순인지
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from src.adapter.base import CardRef, PaymentType, Transaction
from src.common.exceptions import NoVerifiedRuleError
from src.engine.route import evaluate_route, suggest_new_card
from src.repository.card import BenefitRule, Card, Exclusion

AS_OF = date(2026, 8, 25)  # MONTH_START 카드의 실적 기간은 2026-07-01~07-31


def _card(card_id: int, monthly_cap: int | None = None) -> Card:
    return Card(
        id=card_id,
        issuer="테스트카드사",
        name=f"카드{card_id}",
        perf_period_type="MONTH_START",
        billing_offset_days=None,
        monthly_cap=monthly_cap,
        is_demo=True,
    )


def _owned(card_id: int, name: str = "") -> CardRef:
    return CardRef(
        card_id=card_id, issuer="테스트카드사", name=name or f"카드{card_id}", payment_day=25
    )


class TestRanking:
    def test_예상_할인액이_큰_카드가_best다(self):
        card_hi = _card(1)
        card_lo = _card(2)
        rules = {
            1: [BenefitRule(1, 1, 0, None, "ONLINE", Decimal("0.10"), None, 9, True)],
            2: [BenefitRule(2, 2, 0, None, "ALL", Decimal("0.05"), None, 9, True)],
        }
        result = evaluate_route(
            owned_cards=[_owned(1, "고할인카드"), _owned(2, "저할인카드")],
            cards_by_id={1: card_hi, 2: card_lo},
            rules_by_card=rules,
            exclusions_by_card={1: [], 2: []},
            transactions=[],
            amount=100_000,
            category="ONLINE",
            as_of=AS_OF,
        )

        assert result.best.card_id == 1
        assert result.best.expected_discount == 10_000
        assert [c.card_id for c in result.alternatives] == [2]

    def test_미검수_카드는_후보에서_빠지고_개수만_남는다(self):
        verified_card = _card(1)
        unverified_card = _card(2)
        rules = {
            1: [BenefitRule(1, 1, 0, None, "ONLINE", Decimal("0.10"), None, 9, True)],
            2: [BenefitRule(2, 2, 0, None, "ONLINE", Decimal("0.90"), None, None, False)],
        }
        result = evaluate_route(
            owned_cards=[_owned(1), _owned(2)],
            cards_by_id={1: verified_card, 2: unverified_card},
            rules_by_card=rules,
            exclusions_by_card={1: [], 2: []},
            transactions=[],
            amount=100_000,
            category="ONLINE",
            as_of=AS_OF,
        )

        assert result.best.card_id == 1  # 미검수 90% 규칙에 흔들리지 않음
        assert result.alternatives == []
        assert result.compute_meta.candidates_total == 2
        assert result.compute_meta.excluded_unverified_cards == 1

    def test_후보가_전부_사라지면_NoVerifiedRuleError(self):
        unverified_card = _card(1)
        rules = {1: [BenefitRule(1, 1, 0, None, "ONLINE", Decimal("0.10"), None, None, False)]}

        with pytest.raises(NoVerifiedRuleError) as exc_info:
            evaluate_route(
                owned_cards=[_owned(1)],
                cards_by_id={1: unverified_card},
                rules_by_card=rules,
                exclusions_by_card={1: []},
                transactions=[],
                amount=100_000,
                category="ONLINE",
                as_of=AS_OF,
            )
        assert exc_info.value.excluded_cards == 1


class TestPerCardPerformance:
    def test_다른_카드의_거래는_실적에_섞이지_않는다(self):
        # 카드 1: 2단계(0~30만 5%, 30만~ 10%). 카드 2의 큰 거래가 카드 1의
        # 실적에 잘못 합산되면 10% 구간으로 착시가 생긴다.
        card1 = _card(1)
        rules = {
            1: [
                BenefitRule(1, 1, 0, 300_000, "ONLINE", Decimal("0.05"), None, 9, True),
                BenefitRule(2, 1, 300_000, None, "ONLINE", Decimal("0.10"), None, 9, True),
            ],
            2: [BenefitRule(3, 2, 0, None, "ONLINE", Decimal("0.05"), None, 9, True)],
        }
        transactions = [
            Transaction(
                txn_date=date(2026, 7, 10),
                merchant="다른 카드 거래",
                amount=5_000_000,
                category="ONLINE",
                payment_type=PaymentType.LUMP,
                card_id=2,  # 카드 1이 아니다
            ),
        ]

        result = evaluate_route(
            owned_cards=[_owned(1)],
            cards_by_id={1: card1},
            rules_by_card=rules,
            exclusions_by_card={1: [], 2: []},
            transactions=transactions,
            amount=100_000,
            category="ONLINE",
            as_of=AS_OF,
        )

        assert result.best.perf_current == 0
        assert result.best.expected_discount == 5_000  # 5% 구간, 10%가 아님

    def test_실적_제외_거래는_합계에서_빠진다(self):
        card1 = _card(1)
        rules = {
            1: [
                BenefitRule(1, 1, 0, 300_000, "ONLINE", Decimal("0.05"), None, 9, True),
                BenefitRule(2, 1, 300_000, None, "ONLINE", Decimal("0.10"), None, 9, True),
            ]
        }
        exclusions = {1: [Exclusion(1, 1, "PERFORMANCE", "CATEGORY", "TAX", 9, True)]}
        transactions = [
            Transaction(
                txn_date=date(2026, 7, 5),
                merchant="온라인몰",
                amount=250_000,
                category="ONLINE",
                payment_type=PaymentType.LUMP,
                card_id=1,
            ),
            Transaction(
                txn_date=date(2026, 7, 20),
                merchant="세금 납부",
                amount=100_000,
                category="TAX",
                payment_type=PaymentType.LUMP,
                card_id=1,
            ),
        ]

        result = evaluate_route(
            owned_cards=[_owned(1)],
            cards_by_id={1: card1},
            rules_by_card=rules,
            exclusions_by_card=exclusions,
            transactions=transactions,
            amount=100_000,
            category="ONLINE",
            as_of=AS_OF,
        )

        # TAX가 실적에 더해지면 350,000원이 되어 10% 구간으로 넘어간다.
        # 제대로 제외되면 250,000원에 머물러 5% 구간이다.
        assert result.best.perf_current == 250_000
        assert result.best.expected_discount == 5_000

    def test_기간_밖_거래는_실적에_포함되지_않는다(self):
        card1 = _card(1)
        rules = {1: [BenefitRule(1, 1, 300_000, None, "ONLINE", Decimal("0.10"), None, 9, True)]}
        transactions = [
            Transaction(
                txn_date=date(2026, 8, 10),  # 이번 달 — MONTH_START 기간(7월) 밖
                merchant="온라인몰",
                amount=1_000_000,
                category="ONLINE",
                payment_type=PaymentType.LUMP,
                card_id=1,
            ),
        ]

        result = evaluate_route(
            owned_cards=[_owned(1)],
            cards_by_id={1: card1},
            rules_by_card=rules,
            exclusions_by_card={1: []},
            transactions=transactions,
            amount=100_000,
            category="ONLINE",
            as_of=AS_OF,
        )

        assert result.best.perf_current == 0
        assert result.best.perf_achieved is False


class TestNewCardSuggestion:
    def test_보유하지_않은_카드_중_가장_이득이_큰_카드를_고른다(self):
        cards = {
            1: _card(1),
            2: _card(2),
            3: _card(3),
        }
        rules = {
            2: [BenefitRule(1, 2, 0, None, "ONLINE", Decimal("0.05"), None, 9, True)],
            3: [BenefitRule(2, 3, 0, None, "ONLINE", Decimal("0.15"), None, 9, True)],
        }
        suggestion = suggest_new_card(
            owned_card_ids={1},
            cards_by_id=cards,
            rules_by_card=rules,
            exclusions_by_card={2: [], 3: []},
            amount=100_000,
            category="ONLINE",
        )

        assert suggestion is not None
        assert suggestion.card_name == "카드3"
        assert suggestion.expected_gain == 15_000
        assert suggestion.is_affiliate is False

    def test_이득이_0원이면_제안하지_않는다(self):
        cards = {1: _card(1), 2: _card(2)}
        # 30만원 이상부터 적용되는 규칙 — perf=0으로 가정하면 매치되지 않는다.
        rules = {2: [BenefitRule(1, 2, 300_000, None, "ONLINE", Decimal("0.10"), None, 9, True)]}

        suggestion = suggest_new_card(
            owned_card_ids={1},
            cards_by_id=cards,
            rules_by_card=rules,
            exclusions_by_card={2: []},
            amount=100_000,
            category="ONLINE",
        )

        assert suggestion is None

    def test_보유_카드로_조건을_채우면_신규_카드를_제안하지_않는다(self):
        # 보유 카드(1)가 이미 실적을 채운 상태(perf_achieved=True)라면
        # 카드 2가 아무리 유리해도 evaluate_route는 제안을 생략해야 한다.
        card1 = _card(1)
        card2 = _card(2)
        rules = {
            1: [BenefitRule(1, 1, 0, None, "ONLINE", Decimal("0.05"), None, 9, True)],
            2: [BenefitRule(2, 2, 0, None, "ONLINE", Decimal("0.50"), None, 9, True)],
        }

        result = evaluate_route(
            owned_cards=[_owned(1)],
            cards_by_id={1: card1, 2: card2},
            rules_by_card=rules,
            exclusions_by_card={1: [], 2: []},
            transactions=[],
            amount=100_000,
            category="ONLINE",
            as_of=AS_OF,
        )

        assert result.best.perf_achieved is True
        assert result.new_card_suggestion is None

    def test_보유_카드로_조건을_못채우면_evaluate_route가_제안을_채운다(self):
        card1 = _card(1)
        card2 = _card(2)
        rules = {
            1: [BenefitRule(1, 1, 300_000, None, "ONLINE", Decimal("0.10"), None, 9, True)],
            2: [BenefitRule(2, 2, 0, None, "ONLINE", Decimal("0.05"), None, 9, True)],
        }

        result = evaluate_route(
            owned_cards=[_owned(1, "카드1")],
            cards_by_id={1: card1, 2: card2},
            rules_by_card=rules,
            exclusions_by_card={1: [], 2: []},
            transactions=[],  # 실적 0원 -> 카드1은 30만원 문턱을 못 채움
            amount=100_000,
            category="ONLINE",
            as_of=AS_OF,
        )

        assert result.best.perf_achieved is False
        assert result.new_card_suggestion is not None
        assert result.new_card_suggestion.card_name == "카드2"
        assert result.new_card_suggestion.expected_gain == 5_000
