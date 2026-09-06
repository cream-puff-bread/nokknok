"""카테고리별 소비 집계 엔드포인트.

계산이 아니라 집계다. 다른 화면이 전부 "앞으로 어떻게 될지"를 말하는 반면
여기는 "그동안 뭘 썼는지"를 되짚는다(contracts/api-spec.yaml 참조).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from src.api.deps import SessionDep
from src.api.schemas import SpendingSummaryResponse
from src.common.clock import reference_date
from src.repository import spending as spending_repo

router = APIRouter(prefix="/api", tags=["spending"])

# YYYY-MM. FastAPI가 이 패턴으로 거르면 RequestValidationError로 넘어가
# errors.py의 기존 핸들러가 422 INVALID_REQUEST로 바꿔준다 — 이 엔드포인트
# 전용 예외를 새로 만들 이유가 없다.
_MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


@router.get(
    "/spending",
    response_model=SpendingSummaryResponse,
    summary="카테고리별 소비 집계",
)
def get_spending(
    session: SessionDep,
    persona_id: Annotated[int, Query(alias="personaId", description="페르소나 id")],
    month: Annotated[
        str | None,
        Query(pattern=_MONTH_PATTERN, description="YYYY-MM. 생략하면 거래가 있는 마지막 달"),
    ] = None,
) -> SpendingSummaryResponse:
    summary = spending_repo.get_spending_summary(
        session, persona_id, month, today=reference_date()
    )
    return SpendingSummaryResponse.model_validate(summary)
