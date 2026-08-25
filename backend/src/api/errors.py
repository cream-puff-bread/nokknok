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

from src.common.exceptions import (
    InvalidAmountError,
    InvalidCategoryError,
    NoVerifiedRuleError,
    PersonaNotFoundError,
)
from src.common.logging import get_logger

logger = get_logger(__name__)


class ErrorCode(StrEnum):
    """contracts/api-spec.yaml 의 ErrorResponse.code 와 값 집합이 같아야 한다."""

    PERSONA_NOT_FOUND = "PERSONA_NOT_FOUND"
    QUERY_PARSE_FAILED = "QUERY_PARSE_FAILED"
    INVALID_CATEGORY = "INVALID_CATEGORY"
    INVALID_AMOUNT = "INVALID_AMOUNT"
    INVALID_REQUEST = "INVALID_REQUEST"
    NO_VERIFIED_RULE = "NO_VERIFIED_RULE"
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

    @app.exception_handler(NoVerifiedRuleError)
    async def _no_verified_rule(request: Request, exc: NoVerifiedRuleError) -> JSONResponse:
        # 요청은 올바르므로 422 가 아니다. 입력을 고쳐도 달라지지 않는 상황이라
        # 화면이 "입력을 확인하세요"가 아니라 상황 안내를 띄워야 한다.
        logger.warning(
            "검수 통과 규칙 없음 path=%s 제외카드=%d", request.url.path, exc.excluded_cards
        )
        return error_response(
            409,
            ErrorCode.NO_VERIFIED_RULE,
            "지금은 판정에 사용할 수 있는 카드가 없습니다. 규칙 검수가 끝나면 다시 이용할 수 있습니다.",
        )

    @app.exception_handler(InvalidCategoryError)
    async def _invalid_category(request: Request, exc: InvalidCategoryError) -> JSONResponse:
        logger.info("잘못된 카테고리 path=%s category=%s", request.url.path, exc.category)
        return error_response(
            422,
            ErrorCode.INVALID_CATEGORY,
            "존재하지 않는 소비 카테고리입니다.",
        )

    @app.exception_handler(InvalidAmountError)
    async def _invalid_amount(request: Request, exc: InvalidAmountError) -> JSONResponse:
        logger.info("잘못된 금액 path=%s amount=%s", request.url.path, exc.amount)
        return error_response(
            422,
            ErrorCode.INVALID_AMOUNT,
            "금액은 0보다 커야 합니다.",
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
