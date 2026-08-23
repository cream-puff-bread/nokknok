"""FastAPI 애플리케이션 진입점.

`uvicorn src.main:app --reload --port 8000` 으로 기동한다.
자동 생성된 OpenAPI 문서는 /docs 에 노출되며, 이 문서와
contracts/api-spec.yaml 은 항상 같은 커밋에서 함께 갱신한다.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.health import router as health_router
from src.common.config import Settings, get_settings
from src.common.db import dispose_engine
from src.common.logging import get_logger, setup_logging

logger = get_logger(__name__)

_DESCRIPTION = """
가용잔고 산출, 현금흐름 시뮬레이션, 결제 라우팅 최적화 API.

설계 원칙
- 모든 금액은 원 단위 정수이며, 금액 계산은 서버가 전담한다.
- LLM은 질의 해석과 결과 설명에만 관여하며 금액을 계산하지 않는다.
- LLM 생성 실패 시에도 계산 결과는 반드시 응답에 포함된다.
"""


def allowed_origins(raw: str) -> list[str]:
    """CORS_ORIGIN 을 쉼표로 나눠 목록으로 만든다.

    배포하면 Vercel 도메인과 로컬 개발 주소를 동시에 허용해야 하는데 설정값은
    문자열 하나다. 여기서 나눠두면 값이 하나뿐인 지금도 그대로 동작하고,
    배포 시 환경변수만 바꾸면 된다.
    """
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # get_settings() 를 다시 부르면 create_app() 에 주입한 설정이 무시되고
    # 전역 설정으로 돈다. 지금은 로깅뿐이라 무해하지만, 여기에 DB 워밍업이나
    # environment 분기가 들어가는 순간 테스트는 주입값으로 통과하고 배포에서만
    # 다른 값으로 깨진다. 예외 없이 조용히 다른 값이 되는 계열이라 값을 하나만
    # 흐르게 한다.
    settings: Settings = app.state.settings
    logger.info(
        "API 서버 기동 environment=%s db_pool_max=%d",
        settings.environment,
        settings.db_pool_max,
    )
    yield
    # 커넥션을 반환하지 않고 종료하면 무료 티어의 낮은 동시 연결 한도를
    # 배치 스크립트와 나눠 쓰는 상황에서 자리를 잠식한다. Render 는 슬립
    # 전환·재배포 때마다 프로세스를 내리므로 이 경로를 자주 탄다.
    dispose_engine()
    logger.info("API 서버 종료")


def create_app(settings: Settings | None = None) -> FastAPI:
    """앱 인스턴스를 만든다.

    모듈 임포트 시점에 곧바로 만들지 않고 팩토리로 분리한 이유는, 테스트가
    설정을 바꿔가며 앱을 새로 만들 수 있어야 하기 때문이다.
    """
    settings = settings or get_settings()
    setup_logging()

    app = FastAPI(
        title="넉넉(nokknok) API",
        version="0.1.0",
        description=_DESCRIPTION,
        lifespan=lifespan,
    )
    # lifespan 은 앱 인스턴스만 받으므로 설정을 여기에 실어 전달한다.
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins(settings.cors_origin),
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    app.include_router(health_router)
    return app


app = create_app()
