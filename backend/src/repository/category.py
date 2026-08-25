"""소비 카테고리 마스터 조회.

spend_category 코드 집합을 코드에 하드코딩하지 않는다(CLAUDE.md "No hardcoded
enums that mirror DB data"). 카테고리를 추가할 때 여기 손댈 일이 없어야
DB와 코드가 어긋나는 경로가 사라진다.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

_SQL = text("SELECT code FROM spend_category ORDER BY sort_no")


def list_category_codes(session: Session) -> list[str]:
    return [row[0] for row in session.execute(_SQL).all()]
