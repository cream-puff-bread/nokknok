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
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
# fastapi.HTTPException 이 아니라 상위 클래스인 Starlette 쪽에 걸어야 한다.
# 없는 경로(404)와 잘못된 메서드(405)는 라우터가 상위 클래스로 던지므로,
# 하위 클래스에 등록하면 핸들러 탐색이 그것을 찾지 못하고 기본 응답이 나간다.
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.common.exceptions import (
    InvalidAmountError,
    InvalidCategoryError,
    NoVerifiedRuleError,
    PersonaNotFoundError,
    QueryParseError,
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


def error_response(
    status_code: int,
    code: ErrorCode,
    message: str,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(code=code, message=message).model_dump(mode="json"),
        headers=headers,
    )


# 본문을 실을 수 없는 상태 코드. 204 는 "본문 없음"이 정의 자체이고
# 304 는 캐시된 본문을 쓰라는 뜻이라, 둘 다 바디를 붙이면 스펙 위반이다.
_NO_BODY_STATUS = frozenset({204, 304})


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(PersonaNotFoundError)
    async def _persona_not_found(request: Request, exc: PersonaNotFoundError) -> JSONResponse:
        logger.info("페르소나 없음 path=%s", request.url.path)
        return error_response(
            404,
            ErrorCode.PERSONA_NOT_FOUND,
            "요청하신 페르소나를 찾을 수 없습니다.",
        )

    @app.exception_handler(QueryParseError)
    async def _query_parse_failed(request: Request, exc: QueryParseError) -> JSONResponse:
        # 설명 생성 실패와 다르다. 설명은 없어도 숫자를 낼 수 있지만, 질의를
        # 해석하지 못하면 무엇을 계산할지 자체를 모른다.
        logger.info("질의 해석 실패 path=%s 사유=%s", request.url.path, exc.reason)
        return error_response(
            422,
            ErrorCode.QUERY_PARSE_FAILED,
            "질문에서 금액을 찾지 못했습니다. 금액을 포함해 다시 입력해 주세요.",
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

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        """FastAPI 가 직접 던지는 오류도 형식을 맞춘다.

        없는 경로(404), 잘못된 메서드(405), 본문 디코딩 실패(400)는
        RequestValidationError 가 아니라 HTTPException 으로 올라와 기본
        {"detail": ...} 본문이 그대로 나간다. 프론트가 화면 주소를 잘못
        적기만 해도 ApiError 로 파싱되지 않는 응답을 받게 된다.

        상태 코드는 그대로 두고 본문 형식만 바꾼다. HTTP 의미를 유지해야
        브라우저·프록시·keep-alive 가 정상 동작한다.
        """
        logger.info(
            "HTTP 오류 status=%d path=%s", exc.status_code, request.url.path
        )

        # Starlette 기본 핸들러를 대체하므로 그쪽이 붙이던 헤더를 직접 넘겨야
        # 한다. 405 의 Allow 처럼 프로토콜 수준에서 의미가 있는 헤더를 버리면
        # 클라이언트가 "그럼 어떤 메서드를 써야 하나"를 알 방법이 없어진다.
        headers = exc.headers or None

        if exc.status_code in _NO_BODY_STATUS:
            return Response(status_code=exc.status_code, headers=headers)

        if exc.status_code >= 500:
            return error_response(
                exc.status_code,
                ErrorCode.INTERNAL_ERROR,
                "일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
                headers=headers,
            )
        return error_response(
            exc.status_code,
            ErrorCode.INVALID_REQUEST,
            "요청을 처리할 수 없습니다. 입력을 확인해 주세요.",
            headers=headers,
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
