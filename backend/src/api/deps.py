"""엔드포인트 공용 의존성."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.orm import Session

from src.common.db import session_scope


def get_db_session() -> Iterator[Session]:
    """요청 하나에 세션 하나. 응답 후 반드시 반환한다.

    session_scope 가 커밋·롤백과 close 를 함께 처리하므로, 조회 전용
    엔드포인트에서도 커넥션이 새지 않는다. 무료 티어 동시 연결 한도가
    낮아 반환 누락이 곧바로 장애로 이어진다.
    """
    with session_scope() as session:
        yield session
