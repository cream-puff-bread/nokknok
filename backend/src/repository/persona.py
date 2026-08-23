"""페르소나 조회.

API 계층이 직접 쿼리를 실행하지 않도록 데이터 접근을 여기로 모은다.
카드·규칙 조회는 최적화 엔진(@seohee-P)이 이 디렉터리에 따로 추가한다.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.common.exceptions import PersonaNotFoundError

_LIST_SQL = text(
    """
    SELECT p.id,
           p.code,
           p.display_name,
           COALESCE(p.description, '') AS description,
           p.account_balance,
           count(pc.card_id) AS card_count
    FROM persona p
    LEFT JOIN persona_card pc ON pc.persona_id = p.id
    GROUP BY p.id, p.code, p.display_name, p.description, p.account_balance
    ORDER BY p.id
    """
)

# description 을 COALESCE 로 감싸는 이유는 스키마상 NULL 이 가능하지만
# contracts/types.ts 의 Persona.description 은 string 이기 때문이다.
# NULL 을 그대로 내보내면 프론트가 계약에 없는 null 을 다루게 된다.

_CODE_SQL = text("SELECT code FROM persona WHERE id = :persona_id")


@dataclass(frozen=True, slots=True)
class PersonaSummary:
    """목록 화면에 필요한 최소 정보. 거래·확정지출은 포함하지 않는다."""

    id: int
    code: str
    display_name: str
    description: str
    account_balance: int
    card_count: int


def list_personas(session: Session) -> list[PersonaSummary]:
    rows = session.execute(_LIST_SQL).mappings().all()
    return [
        PersonaSummary(
            id=r["id"],
            code=r["code"],
            display_name=r["display_name"],
            description=r["description"],
            account_balance=r["account_balance"],
            card_count=r["card_count"],
        )
        for r in rows
    ]


def get_persona_code(session: Session, persona_id: int) -> str:
    """id 를 어댑터가 쓰는 source_key(페르소나 code)로 바꾼다.

    TransactionProvider.fetch 는 source_key 하나만 받고 그 의미는 구현체마다
    다르다. MockProvider 는 페르소나 code, FileProvider 는 업로드 파일 경로다.
    어댑터 쪽에 id 개념을 넣으면 FileProvider 에서 의미가 없어지므로,
    계약(personaId)과 어댑터(source_key) 사이의 간극은 이 계층에서 흡수한다.
    """
    code = session.execute(_CODE_SQL, {"persona_id": persona_id}).scalar_one_or_none()
    if code is None:
        raise PersonaNotFoundError(persona_id)
    return code
