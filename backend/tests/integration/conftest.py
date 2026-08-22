"""통합 테스트 공통 픽스처.

이 디렉터리의 테스트는 실제 DB에 연결한다. `tests/` 최상위의 단위 테스트(스텁·목
기반)와 성격이 다르므로 별도 폴더와 `integration` 마커로 분리했다.

DATABASE_URL이 없거나 연결에 실패하면 세션 시작 시점에 이 폴더의 모든 테스트가
자동으로 skip된다. 개별 테스트마다 연결을 시도하고 실패하도록 두면 오류 메시지가
테스트 수만큼 반복돼 원인 파악이 오히려 어려워진다.

`db_session` 은 트랜잭션을 연 뒤 테스트가 끝나면 무조건 롤백한다. MockProvider와
RuleLoader 모두 session.commit()을 직접 호출하지 않으므로(커밋은 상위 계층인
session_scope()의 책임이다), 바깥 트랜잭션만 롤백하면 테스트 중 INSERT가 실제
시드 데이터를 건드리지 않는다.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from src.common.config import get_settings
from src.common.db import dispose_engine, get_engine


def _connectable() -> tuple[bool, str]:
    settings = get_settings()
    if not settings.database_url:
        return False, "DATABASE_URL이 설정되지 않았습니다"
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, ""
    except Exception as exc:  # noqa: BLE001 - 연결 실패 사유를 skip 메시지로 그대로 전달
        return False, f"DB 연결 실패: {exc}"


@pytest.fixture(scope="session", autouse=True)
def _require_db() -> Iterator[None]:
    ok, reason = _connectable()
    if not ok:
        pytest.skip(f"통합 테스트 skip: {reason}")
    yield
    dispose_engine()


@pytest.fixture(scope="session")
def db_engine() -> Engine:
    """격리 증명 테스트처럼 db_session과 별도로 연결이 필요할 때 쓴다."""
    return get_engine()


@pytest.fixture
def db_session(db_engine: Engine) -> Iterator[Session]:
    """트랜잭션 하나를 열고 테스트 종료 시 항상 롤백하는 세션."""
    connection = db_engine.connect()
    trans = connection.begin()
    session = sessionmaker(bind=connection)()
    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        connection.close()
