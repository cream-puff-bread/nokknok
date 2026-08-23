"""헬스체크 엔드포인트.

Render 무료 인스턴스는 15분 무응답 시 슬립되고 재기동에 30~60초가 걸린다.
심사 기간 중 URL 접근 불가는 결격 사유이므로 .github/workflows/keep-alive.yml 이
10분마다 이 엔드포인트를 호출해 인스턴스를 깨워둔다.

DB를 조회하지 않는다. 이 엔드포인트가 답해야 하는 질문은 "인스턴스가 깨어
있는가" 하나다. DB 조회를 넣으면 10분마다 커넥션을 하나씩 잡아 무료 티어의
낮은 동시 연결 한도를 갉아먹고, DB가 잠깐 불안정할 때 인스턴스는 멀쩡한데도
keep-alive 가 실패로 보고한다. DB 상태 점검이 필요해지면 별도 경로로 분리한다.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["health"])


class HealthResponse(BaseModel):
    """contracts/api-spec.yaml 의 /api/health 응답과 1:1 대응한다."""

    status: str
    time: datetime


@router.get("/health", response_model=HealthResponse, summary="헬스체크 (keep-alive용)")
def health() -> HealthResponse:
    return HealthResponse(status="ok", time=datetime.now(UTC))
