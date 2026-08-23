"""오류 응답 형식 통일.

FastAPI 기본 오류 본문은 검증 실패 시 {"detail": [...]}, 처리되지 않은 예외 시
{"detail": "Internal Server Error"} 다. contracts/api-spec.yaml 이 규정한
ErrorResponse({code, message})와 형식이 달라, 이대로 두면 프론트가 두 가지
형태를 모두 다뤄야 한다. 여기서 전부 ErrorResponse 로 바꾼다.

message 는 화면에 그대로 노출되는 안내 문구다. 예외 원문이나 스택을 싣지 않는다
(contracts/ui-system.md — "오류 원문 노출 금지"). 원인 파악에 필요한 정보는
로그로만 남긴다.
"""

from __future__ import annotations

from enum import StrEnum

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.common.exceptions import PersonaNotFoundError
from src.common.logging import get_logger

logger = get_logger(__name__)


class ErrorCode(StrEnum):
    """contracts/api-spec.yaml 의 ErrorResponse.code 와 값 집합이 같아야 한다."""

    PERSONA_NOT_FOUND = "PERSONA_NOT_FOUND"
    QUERY_PARSE_FAILED = "QUERY_PARSE_FAILED"
    INVALID_CATEGORY = "INVALID_CATEGORY"
    INVALID_AMOUNT = "INVALID_AMOUNT"
    INVALID_REQUEST = "INVALID_REQUEST"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ErrorResponse(BaseModel):
    code: ErrorCode
    message: str


def error_response(status_code: int, code: ErrorCode, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(code=code, message=message).model_dump(mode="json"),
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(PersonaNotFoundError)
    async def _persona_not_found(request: Request, exc: PersonaNotFoundError) -> JSONResponse:
        logger.info("페르소나 없음 path=%s", request.url.path)
        return error_response(
            404,
            ErrorCode.PERSONA_NOT_FOUND,
            "요청하신 페르소나를 찾을 수 없습니다.",
        )

    @app.exception_handler(RequestValidationError)
    async def _invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        # 어느 필드가 왜 틀렸는지는 로그로만 남긴다. 응답에 그대로 실으면
        # 내부 필드명이 노출되고 형식도 ErrorResponse 를 벗어난다.
        logger.info("요청 검증 실패 path=%s errors=%s", request.url.path, exc.errors())
        return error_response(
            422,
            ErrorCode.INVALID_REQUEST,
            "요청 값을 확인해 주세요.",
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # 시연 중 예외가 그대로 500 기본 본문으로 나가면 화면이 오류 원문을
        # 띄우거나 파싱에 실패한다. 형식을 맞춘 안내 문구로 대체한다.
        logger.exception("처리되지 않은 오류 path=%s", request.url.path)
        return error_response(
            500,
            ErrorCode.INTERNAL_ERROR,
            "일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
        )
