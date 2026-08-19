"""데이터베이스 연결.

무료 티어는 동시 연결 한도가 낮다. 두 가지를 반드시 지킨다.

1. 연결 문자열은 풀링(Pooled) 주소를 쓴다.
2. 애플리케이션 풀 상한을 작게 잡고 max_overflow=0 으로 초과 생성을 막는다.

max_overflow 를 명시하지 않으면 SQLAlchemy 기본값(10)이 적용되어
pool_size 를 5로 잡아도 실제로는 15개까지 열린다. 상한이 지켜지지 않는다.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.common.config import get_settings
from src.common.logging import get_logger

logger = get_logger(__name__)

_engine: Engine | None = None
_SessionFactory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    """프로세스당 하나의 엔진을 공유한다."""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(
            settings.require_database_url(),
            pool_size=settings.db_pool_max,
            max_overflow=0,  # 상한을 실제로 강제하기 위해 반드시 0
            pool_timeout=settings.db_pool_timeout_s,
            pool_pre_ping=True,  # 슬립 후 끊긴 커넥션을 재사용하지 않도록
            future=True,
        )
        logger.info(
            "DB 엔진 생성 (pool_size=%d, max_overflow=0)", settings.db_pool_max
        )
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionFactory


@contextmanager
def session_scope() -> Iterator[Session]:
    """트랜잭션 범위를 감싸는 컨텍스트 매니저.

    정상 종료 시 커밋, 예외 발생 시 롤백하고 항상 연결을 반환한다.
    """
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def dispose_engine() -> None:
    """엔진과 풀을 완전히 해제한다.

    배치 스크립트는 작업이 끝나면 반드시 호출한다.
    호출하지 않으면 커넥션이 반환되지 않은 채 프로세스가 종료되어,
    API 서버가 붙을 자리를 잠식한다.
    """
    global _engine, _SessionFactory
    if _engine is not None:
        _engine.dispose()
        logger.info("DB 엔진 해제")
    _engine = None
    _SessionFactory = None
