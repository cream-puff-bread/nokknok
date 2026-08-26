"""6개월 현금흐름 시뮬레이션 엔드포인트.

CONTRIBUTING.md 의 조립 원칙을 그대로 따른다 — 계산은 예측 모듈이, 해석은
LLM 이, 조립은 이 계층이 한다. 라우터는 쿼리를 직접 실행하지 않고 금액을
계산하지도 않는다.

처리 순서와 실패 시 동작:

| 단계 | 실패 시 |
|---|---|
| 1. personaId -> 페르소나 code | 404 PERSONA_NOT_FOUND |
| 2. 질의 해석 (LLM)             | 422 QUERY_PARSE_FAILED |
| 3. 잔고 추이 계산              | 500 (계산은 실패하면 안 되는 경로다) |

페르소나 조회를 먼저 하는 이유는, 둘 다 잘못됐을 때 "없는 페르소나"가
이용자가 고칠 수 있는 더 분명한 오류이기 때문이다. LLM 호출을 하기 전에
걸러내므로 예산도 아낀다.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from src.adapter.factory import SourceKind, build_provider
from src.api.deps import SessionDep, get_query_parser
from src.api.query_parser import ParsedQuery, QueryParser
from src.api.schemas import (
    DeadPointResponse,
    ForecastMetaResponse,
    ParsedQueryResponse,
    ScenarioPointResponse,
    ScenarioResponse,
    SimulateRequest,
    SimulationResponse,
)
from src.common.logging import get_logger
from src.forecast import CashflowForecast, forecast_cashflow
from src.repository import persona as persona_repo

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["simulate"])

ParserDep = Annotated[QueryParser, Depends(get_query_parser)]


def _to_response(parsed: ParsedQuery, forecast: CashflowForecast) -> SimulationResponse:
    return SimulationResponse(
        parsed=ParsedQueryResponse(
            amount=parsed.amount,
            payment_type=parsed.payment_type,
            installment_months=parsed.installment_months,
            category=parsed.category,
        ),
        scenarios=[
            ScenarioResponse(
                level=scenario.level,
                points=[
                    ScenarioPointResponse(month=p.month, balance=p.balance)
                    for p in scenario.points
                ],
            )
            for scenario in forecast.scenarios
        ],
        dead_point=(
            DeadPointResponse(
                month=forecast.dead_point.month,
                level=forecast.dead_point.level,
                shortage=forecast.dead_point.shortage,
            )
            if forecast.dead_point is not None
            else None
        ),
        forecast_meta=ForecastMetaResponse(
            months_used=forecast.meta.months_used,
            txn_count=forecast.meta.txn_count,
            cold_start=forecast.meta.cold_start,
        ),
    )


@router.post(
    "/simulate", response_model=SimulationResponse, summary="6개월 현금흐름 시뮬레이션"
)
def simulate(
    body: SimulateRequest, session: SessionDep, parser: ParserDep
) -> SimulationResponse:
    code = persona_repo.get_persona_code(session, body.persona_id)
    parsed = parser.parse(body.query)

    snapshot = build_provider(SourceKind.MOCK, session=session).fetch(code)
    forecast = forecast_cashflow(snapshot, purchase=parsed.to_purchase())

    logger.info(
        "시뮬레이션 완료 persona_id=%d 적자전환=%s",
        body.persona_id,
        forecast.dead_point.month if forecast.dead_point else "없음",
    )
    return _to_response(parsed, forecast)
