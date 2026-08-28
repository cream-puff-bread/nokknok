"""근거 조항 조회.

card_benefit_rule.clause_id로 clause_source를 직접 조인한다. 벡터 검색을
쓰지 않는 이유는 docs/decisions/001 참조 — 규칙과 조항의 연결이 배치
적재 시점에 이미 확정돼 있어(clause_id 컬럼), 여기서는 그 id로 원문을
가져오기만 하면 된다.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

_SQL = text("SELECT content, doc_name, page_no FROM clause_source WHERE id = :clause_id")


@dataclass(frozen=True, slots=True)
class ClauseRef:
    content: str
    doc_name: str
    page_no: int | None


def get_clause(session: Session, clause_id: int) -> ClauseRef | None:
    row = session.execute(_SQL, {"clause_id": clause_id}).mappings().first()
    if row is None:
        return None
    return ClauseRef(content=row["content"], doc_name=row["doc_name"], page_no=row["page_no"])
