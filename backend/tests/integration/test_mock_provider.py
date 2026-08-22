"""MockProvider 통합 테스트.

data/personas.seed.sql로 적재된 실제 페르소나 3종(SUBSCRIPTION_HEAVY,
INSTALLMENT_HEAVY, STABLE)을 실제 DB에서 조회해 FinancialSnapshot이
올바르게 구성되는지 확인한다. 단위 테스트(test_adapter.py)는 FileProvider를
목 데이터로 다루므로, DB 조회 SQL 자체가 스키마와 맞는지는 여기서만 검증된다.
"""

from __future__ import annotations

from datetime import date

import pytest

from src.adapter.base import ExpenseType, FinancialSnapshot
from src.adapter.mock_provider import MockProvider
from src.common.exceptions import PersonaNotFoundError

pytestmark = pytest.mark.integration

PERSONA_CODES = ("SUBSCRIPTION_HEAVY", "INSTALLMENT_HEAVY", "STABLE")


class TestMockProviderSnapshot:
    @pytest.mark.parametrize("code", PERSONA_CODES)
    def test_페르소나_3종을_조회하면_FinancialSnapshot이_정상_구성된다(
        self, db_session, code
    ):
        provider = MockProvider(db_session)
        snapshot = provider.fetch(code)

        assert isinstance(snapshot, FinancialSnapshot)
        assert snapshot.account_balance > 0
        assert snapshot.monthly_income > 0
        assert 1 <= snapshot.income_day <= 28
        # 세 페르소나 모두 personas.seed.sql에서 카드·거래·확정지출을 갖는다.
        assert len(snapshot.cards) > 0
        assert len(snapshot.transactions) > 0
        assert len(snapshot.fixed_expenses) > 0

    def test_존재하지_않는_페르소나는_예외를_던진다(self, db_session):
        provider = MockProvider(db_session)
        with pytest.raises(PersonaNotFoundError):
            provider.fetch("NOT_A_REAL_PERSONA")


class TestAvailableBalance:
    @pytest.mark.parametrize("code", PERSONA_CODES)
    def test_available_balance는_계좌잔액에서_확정지출_합계를_뺀_값이다(
        self, db_session, code
    ):
        provider = MockProvider(db_session)
        snapshot = provider.fetch(code)

        fixed_total = sum(e.amount for e in snapshot.fixed_expenses)
        assert snapshot.fixed_total == fixed_total
        assert snapshot.available_balance == snapshot.account_balance - fixed_total


class TestUnusedSuspect:
    def test_unused_suspect은_구독이면서_90일_이상_미사용인_경우에만_True(
        self, db_session
    ):
        provider = MockProvider(db_session)
        snapshot = provider.fetch("SUBSCRIPTION_HEAVY")

        subs = [
            e
            for e in snapshot.fixed_expenses
            if e.expense_type is ExpenseType.SUBSCRIPTION
        ]
        # 이 페르소나는 구독 과다형으로 설계됐으므로 구독 항목이 있어야
        # 이 테스트 자체가 의미를 갖는다.
        assert subs

        for expense in subs:
            expected = (
                expense.last_used_date is not None
                and (date.today() - expense.last_used_date).days >= 90
            )
            assert expense.unused_suspect == expected

        # personas.seed.sql의 '영상 스트리밍 B'(2026-03-02), '전자책 구독'
        # (2026-01-20)은 오늘(2026-08-20 이후 어느 시점이든) 기준 90일을
        # 이미 넘겼으므로 최소 하나는 미사용 의심으로 판정돼야 한다.
        assert any(e.unused_suspect for e in subs)

    def test_비구독_항목은_last_used_date와_무관하게_False(self, db_session):
        provider = MockProvider(db_session)
        snapshot = provider.fetch("SUBSCRIPTION_HEAVY")

        non_subs = [
            e
            for e in snapshot.fixed_expenses
            if e.expense_type is not ExpenseType.SUBSCRIPTION
        ]
        assert non_subs  # 이 페르소나는 보험·대출도 함께 갖는다
        assert all(not e.unused_suspect for e in non_subs)
