"""카드 규칙 조회 통합 테스트.

data/cards.seed.sql·clauses.seed.sql로 적재된 실제 카드 A/B/C를 대상으로
repository/card.py의 조회 SQL이 스키마와 맞는지, 그리고 clause_id가
비어 있지 않은지(근거 표시 요구사항, backend/README.md) 확인한다.
"""

from __future__ import annotations

import pytest

from src.repository.card import get_cards, list_benefit_rules, list_exclusions

pytestmark = pytest.mark.integration

DEMO_CARD_IDS = [1, 2, 3]


class TestCardRepository:
    def test_카드_3종을_조회한다(self, db_session):
        cards = get_cards(db_session, DEMO_CARD_IDS)

        assert {c.id for c in cards} == set(DEMO_CARD_IDS)
        assert all(c.is_demo for c in cards)

    def test_카드가_없으면_빈_리스트를_반환한다(self, db_session):
        assert get_cards(db_session, []) == []
        assert list_benefit_rules(db_session, []) == []
        assert list_exclusions(db_session, []) == []

    def test_모든_혜택_규칙에_근거_조항이_연결돼_있다(self, db_session):
        rules = list_benefit_rules(db_session, DEMO_CARD_IDS)

        assert len(rules) > 0
        missing = [r.id for r in rules if r.clause_id is None]
        assert missing == [], f"근거 조항 없는 규칙: {missing}"

    def test_모든_제외_항목에_근거_조항이_연결돼_있다(self, db_session):
        exclusions = list_exclusions(db_session, DEMO_CARD_IDS)

        assert len(exclusions) > 0
        missing = [e.id for e in exclusions if e.clause_id is None]
        assert missing == [], f"근거 조항 없는 제외 항목: {missing}"

    def test_카드_C_규칙_개수는_시드와_일치한다(self, db_session):
        rules = [r for r in list_benefit_rules(db_session, [3]) if r.verified]
        assert len(rules) == 4  # ONLINE, DELIVERY, CAFE, ALL
