"""데이터 소스 구현체 선택.

상위 계층은 팩토리만 호출하고 어떤 구현체가 반환되는지 알지 못한다.
사업화 단계에서 MyDataProvider 를 추가할 때 이 파일 한 곳만 수정하면 된다.
"""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy.orm import Session

from src.adapter.base import TransactionProvider
from src.adapter.file_provider import FileProvider
from src.adapter.mock_provider import MockProvider


class SourceKind(StrEnum):
    MOCK = "mock"
    FILE = "file"
    # MYDATA = "mydata"  # 사업화 단계에서 추가


def build_provider(
    kind: SourceKind,
    session: Session | None = None,
    account_balance: int = 0,
    monthly_income: int = 0,
) -> TransactionProvider:
    """구현체를 생성한다.

    MockProvider 는 DB 세션이 필요하고 FileProvider 는 필요 없다.
    이 차이를 팩토리가 흡수해 호출부가 신경 쓰지 않도록 한다.
    """
    if kind is SourceKind.MOCK:
        if session is None:
            raise ValueError("MockProvider 에는 DB 세션이 필요합니다")
        return MockProvider(session)

    if kind is SourceKind.FILE:
        return FileProvider(
            account_balance=account_balance, monthly_income=monthly_income
        )

    raise ValueError(f"지원하지 않는 데이터 소스입니다: {kind}")
