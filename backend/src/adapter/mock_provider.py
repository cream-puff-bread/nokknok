"""시연용 목 어댑터.

DB에 적재된 가상 페르소나 데이터를 마이데이터 표준 규격 형태로 반환한다.
실제 마이데이터 연동에는 본인신용정보관리업 허가가 필요하므로,
MVP 단계에서는 동일한 응답 형식을 따르는 이 구현체로 시연한다.

응답 형식이 표준을 따르므로 사업화 단계에서 구현체만 교체하면
상위 로직은 수정할 필요가 없다.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.adapter.base import (
    CardRef,
    ExpenseType,
    FinancialSnapshot,
    FixedExpense,
    PaymentType,
    Transaction,
)
from src.common.exceptions import PersonaNotFoundError
from src.common.logging import get_logger

logger = get_logger(__name__)


_PERSONA_SQL = text(
    """
    SELECT id, code, display_name, account_balance, monthly_income, income_day
    FROM persona
    WHERE code = :code
    """
)

_CARD_SQL = text(
    """
    SELECT c.id, c.issuer, c.name, pc.payment_day, c.is_demo
    FROM persona_card pc
    JOIN card c ON c.id = pc.card_id
    WHERE pc.persona_id = :persona_id
    ORDER BY c.id
    """
)

_TXN_SQL = text(
    """
    SELECT txn_date, merchant, amount, category, payment_type,
           card_id, installment_months, is_recurring
    FROM transaction
    WHERE persona_id = :persona_id
    ORDER BY txn_date DESC
    """
)

_FIXED_SQL = text(
    """
    SELECT expense_type, label, amount, charge_day,
           remaining_months, last_used_date, card_id
    FROM fixed_expense
    WHERE persona_id = :persona_id
    ORDER BY charge_day
    """
)


class MockProvider:
    """페르소나 code 로 조회하는 시연용 구현체."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def fetch(self, source_key: str) -> FinancialSnapshot:
        """source_key 는 페르소나 code 다. 예: SUBSCRIPTION_HEAVY"""
        persona = self._session.execute(
            _PERSONA_SQL, {"code": source_key}
        ).mappings().first()

        if persona is None:
            raise PersonaNotFoundError(source_key)

        persona_id = persona["id"]
        logger.info("페르소나 조회 code=%s", source_key)

        return FinancialSnapshot(
            account_balance=persona["account_balance"],
            monthly_income=persona["monthly_income"],
            income_day=persona["income_day"],
            cards=self._fetch_cards(persona_id),
            transactions=self._fetch_transactions(persona_id),
            fixed_expenses=self._fetch_fixed(persona_id),
        )

    # ---------- internal ----------
    def _fetch_cards(self, persona_id: int) -> list[CardRef]:
        rows = self._session.execute(
            _CARD_SQL, {"persona_id": persona_id}
        ).mappings().all()
        return [
            CardRef(
                card_id=r["id"],
                issuer=r["issuer"],
                name=r["name"],
                payment_day=r["payment_day"],
                is_demo=r["is_demo"],
            )
            for r in rows
        ]

    def _fetch_transactions(self, persona_id: int) -> list[Transaction]:
        rows = self._session.execute(
            _TXN_SQL, {"persona_id": persona_id}
        ).mappings().all()
        return [
            Transaction(
                txn_date=r["txn_date"],
                merchant=r["merchant"],
                amount=r["amount"],
                category=r["category"],
                payment_type=PaymentType(r["payment_type"]),
                card_id=r["card_id"],
                installment_months=r["installment_months"],
                is_recurring=r["is_recurring"],
            )
            for r in rows
        ]

    def _fetch_fixed(self, persona_id: int) -> list[FixedExpense]:
        rows = self._session.execute(
            _FIXED_SQL, {"persona_id": persona_id}
        ).mappings().all()
        return [
            FixedExpense(
                expense_type=ExpenseType(r["expense_type"]),
                label=r["label"],
                amount=r["amount"],
                charge_day=r["charge_day"],
                remaining_months=r["remaining_months"],
                last_used_date=r["last_used_date"],
                card_id=r["card_id"],
            )
            for r in rows
        ]
