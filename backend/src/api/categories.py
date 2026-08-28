"""소비 카테고리 목록 엔드포인트.

카테고리 코드는 DB(spend_category) 소유 값이라 화면이 지어낼 수 없다
(CLAUDE.md "No hardcoded enums that mirror DB data"). 이 엔드포인트가 없으면
화면은 코드를 자유 입력으로 받을 수밖에 없고, 이용자가 "온라인"처럼 그럴듯한
값을 치면 INVALID_CATEGORY 로 되돌아온다 — 고를 수 있는 값을 알려주지 않고
틀렸다고만 답하는 셈이다.

계산이 없으므로 LLM·엔진과 무관하다.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.api.deps import get_db_session
from src.api.schemas import SpendCategoryResponse
from src.repository import category as category_repo

router = APIRouter(prefix="/api", tags=["categories"])

SessionDep = Annotated[Session, Depends(get_db_session)]


@router.get(
    "/categories",
    response_model=list[SpendCategoryResponse],
    summary="소비 카테고리 목록",
)
def list_categories(session: SessionDep) -> list[SpendCategoryResponse]:
    # 규칙 매칭용 와일드카드(ALL)는 결제 카테고리가 아니므로 빠진다
    # (repository/category.py 참조).
    return [
        SpendCategoryResponse.model_validate(c)
        for c in category_repo.list_purchase_categories(session)
    ]
