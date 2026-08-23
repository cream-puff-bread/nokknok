"""페르소나 목록과 가용잔고 엔드포인트.

두 엔드포인트 모두 페르소나 단위 조회라 한 라우터에 둔다.
계산은 하지 않는다. 가용잔고 산출은 어댑터가 반환한 FinancialSnapshot 의
책임이고 여기서는 응답 형식으로 옮기기만 한다.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.adapter.factory import SourceKind, build_provider
from src.api.deps import get_db_session
from src.api.schemas import BalanceResponse, FixedExpenseResponse, PersonaResponse
from src.common.logging import get_logger
from src.repository import persona as persona_repo

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["personas"])

SessionDep = Annotated[Session, Depends(get_db_session)]


@router.get("/personas", response_model=list[PersonaResponse], summary="시연용 페르소나 목록")
def list_personas(session: SessionDep) -> list[PersonaResponse]:
    rows = persona_repo.list_personas(session)
    return [PersonaResponse.model_validate(row) for row in rows]


@router.get("/balance", response_model=BalanceResponse, summary="가용잔고 조회")
def get_balance(
    session: SessionDep,
    persona_id: Annotated[int, Query(alias="personaId", description="페르소나 id")],
) -> BalanceResponse:
    # 계약은 personaId(int)를 받고 어댑터는 source_key(str)를 받는데, source_key 의
    # 의미는 구현체마다 다르다(MockProvider 는 페르소나 code, FileProvider 는 파일
    # 경로). 어댑터에 id 개념을 넣으면 FileProvider 에서 의미가 없어지므로 이
    # 계층에서 변환한다. 팀 합의 사항이다.
    code = persona_repo.get_persona_code(session, persona_id)

    # 상위 계층은 어떤 구현체가 붙었는지 알지 못해야 한다. 실제 마이데이터
    # 연동으로 바뀌어도 이 줄의 SourceKind 만 달라진다.
    provider = build_provider(SourceKind.MOCK, session=session)
    snapshot = provider.fetch(code)

    logger.info(
        "가용잔고 조회 persona_id=%d 확정지출=%d건",
        persona_id,
        len(snapshot.fixed_expenses),
    )

    return BalanceResponse(
        account_balance=snapshot.account_balance,
        fixed_total=snapshot.fixed_total,
        available_balance=snapshot.available_balance,
        fixed_expenses=[
            FixedExpenseResponse.model_validate(e) for e in snapshot.fixed_expenses
        ],
    )
