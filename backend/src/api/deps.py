"""엔드포인트 공용 의존성."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from src.api.query_parser import QueryParser, build_query_parser
from src.common.db import session_scope
from src.repository import category as category_repo


def get_db_session() -> Iterator[Session]:
    """요청 하나에 세션 하나. 응답 후 반드시 반환한다.

    session_scope 가 커밋·롤백과 close 를 함께 처리하므로, 조회 전용
    엔드포인트에서도 커넥션이 새지 않는다. 무료 티어 동시 연결 한도가
    낮아 반환 누락이 곧바로 장애로 이어진다.
    """
    with session_scope() as session:
        yield session


SessionDep = Annotated[Session, Depends(get_db_session)]


def get_query_parser(session: SessionDep) -> QueryParser:
    """질의 해석기를 의존성으로 만든다.

    라우터 안에서 직접 생성하면 테스트가 LLM 을 호출하지 않고는 엔드포인트를
    검증할 수 없다. 의존성으로 빼면 오버라이드로 갈아끼울 수 있다.

    카테고리 enum 은 spend_category 마스터에서 읽는다. 코드에 목록을 다시
    적으면 카테고리를 추가할 때 한쪽을 빠뜨린다.
    """
    return build_query_parser(category_repo.list_category_codes(session))
