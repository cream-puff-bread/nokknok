"""소비 카테고리 마스터 조회.

카테고리 코드를 코드에 다시 적으면 spend_category 가 바뀔 때 조용히 어긋난다.
LLM 응답 스키마의 enum 은 이 목록으로 만든다.

배치 경로에도 같은 성격의 조회가 있다(src/rag/category_schema.py). 그쪽은
Gemini Schema 구성까지 함께 하므로 지금은 분리해 두었다 — 하나로 합칠지는
런타임 스키마가 자리를 잡은 뒤 @mango606 과 정한다.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

_CATEGORY_SQL = text("SELECT code FROM spend_category ORDER BY sort_no")

_cached: tuple[str, ...] | None = None


def list_category_codes(session: Session, *, refresh: bool = False) -> tuple[str, ...]:
    """spend_category.code 전체.

    요청마다 DB를 왕복할 이유가 없다. 마스터는 배포 중에 바뀌지 않으므로
    프로세스 생애주기 동안 캐싱한다. 테스트에서 값을 바꿔야 하면
    refresh=True 를 쓴다.
    """
    global _cached
    if _cached is None or refresh:
        _cached = tuple(r[0] for r in session.execute(_CATEGORY_SQL).all())
    return _cached


def reset_cache() -> None:
    """테스트에서 캐시를 비운다."""
    global _cached
    _cached = None
