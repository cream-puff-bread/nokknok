"""오류 응답 형식 테스트.

DB 없이 돈다. 세션 의존성은 오버라이드해 실제 연결을 만들지 않는다.
"""

from __future__ import annotations

import pytest
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.testclient import TestClient

from src.api.deps import get_db_session
from src.api.errors import ErrorCode
from src.common.exceptions import NoVerifiedRuleError, PersonaNotFoundError
from src.main import create_app


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    # 검증 실패 경로에서도 의존성 해석은 일어난다. 실제 DB 를 만들지 않도록 막는다.
    app.dependency_overrides[get_db_session] = lambda: None
    return TestClient(app, raise_server_exceptions=False)


def test_요청_형식_오류는_422와_INVALID_REQUEST다(client: TestClient):
    """personaId 에 정수가 아닌 값이 오면 FastAPI 가 검증 실패를 낸다.

    기본 본문은 {"detail": [...]} 라 contracts 의 ErrorResponse 와 형식이 다르다.
    프론트가 두 형태를 모두 다루지 않도록 여기서 통일한다.
    """
    response = client.get("/api/balance", params={"personaId": "abc"})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == ErrorCode.INVALID_REQUEST
    assert body["message"]
    assert "detail" not in body


def test_필수_파라미터_누락도_INVALID_REQUEST다(client: TestClient):
    response = client.get("/api/balance")

    assert response.status_code == 422
    assert response.json()["code"] == ErrorCode.INVALID_REQUEST


def test_페르소나_없음은_404와_PERSONA_NOT_FOUND다(client: TestClient):
    def _raise() -> None:
        raise PersonaNotFoundError(999)

    client.app.dependency_overrides[get_db_session] = _raise  # type: ignore[attr-defined]

    response = client.get("/api/balance", params={"personaId": 999})

    assert response.status_code == 404
    assert response.json()["code"] == ErrorCode.PERSONA_NOT_FOUND


def test_검수_통과_규칙_없음은_409와_NO_VERIFIED_RULE다(client: TestClient):
    """요청은 올바르므로 422 와 구분한다.

    422 는 입력을 고치면 해결되지만 이 경우는 이용자가 무엇을 바꿔도
    달라지지 않는다. 상태 코드가 같으면 화면이 "입력을 확인하세요"와
    "지금은 판정할 수 없습니다"를 구분할 근거를 잃는다.
    """

    def _raise() -> None:
        raise NoVerifiedRuleError(excluded_cards=3)

    client.app.dependency_overrides[get_db_session] = _raise  # type: ignore[attr-defined]

    response = client.get("/api/personas")

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == ErrorCode.NO_VERIFIED_RULE
    # 제외 카드 수 같은 내부 수치를 안내 문구에 노출하지 않는다.
    assert "3" not in body["message"]


def test_처리되지_않은_예외는_500과_INTERNAL_ERROR다(client: TestClient):
    """예외 원문이 응답에 실리면 안 된다.

    시연 중 스택이나 DB 오류 문구가 화면에 뜨면 그대로 심사에 노출된다.
    """
    secret = "psycopg.OperationalError: password authentication failed"

    def _raise() -> None:
        raise RuntimeError(secret)

    client.app.dependency_overrides[get_db_session] = _raise  # type: ignore[attr-defined]

    response = client.get("/api/personas")

    assert response.status_code == 500
    body = response.json()
    assert body["code"] == ErrorCode.INTERNAL_ERROR
    assert secret not in body["message"]
    assert "detail" not in body


def test_오류_코드_집합이_계약과_같다():
    """contracts/api-spec.yaml 의 ErrorResponse.code enum 과 값이 어긋나면
    프론트가 분기할 수 없는 코드가 응답에 실린다.
    """
    from pathlib import Path

    spec = (
        Path(__file__).resolve().parents[2] / "contracts" / "api-spec.yaml"
    ).read_text(encoding="utf-8")

    for code in ErrorCode:
        assert f"- {code.value}" in spec, f"api-spec.yaml 에 {code.value} 가 없다"


def test_없는_경로도_ErrorResponse_형식이다(client: TestClient):
    """FastAPI 기본 404 는 {"detail": "Not Found"} 라 ApiError 로 파싱되지 않는다.

    프론트가 화면 주소를 잘못 적기만 해도 계약을 벗어난 응답을 받는다.
    """
    response = client.get("/api/nope")

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == ErrorCode.INVALID_REQUEST
    assert "detail" not in body


def test_잘못된_메서드도_ErrorResponse_형식이다(client: TestClient):
    response = client.post("/api/personas")

    assert response.status_code == 405
    assert response.json()["code"] == ErrorCode.INVALID_REQUEST


def test_본문_디코딩_실패도_ErrorResponse_형식이다(client: TestClient):
    """잘못된 UTF-8 본문은 RequestValidationError 가 아니라 HTTPException 이다."""
    response = client.post(
        "/api/simulate",
        content=b'{"personaId":2,"query":"' + bytes([0xC0, 0xCE]) + b'"}',
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["code"] == ErrorCode.INVALID_REQUEST
    assert "detail" not in body


def test_405에_Allow_헤더가_남는다(client: TestClient):
    """Starlette 기본 핸들러를 대체하므로 그쪽이 붙이던 헤더를 직접 넘겨야 한다.

    Allow 를 버리면 클라이언트가 "그럼 어떤 메서드를 써야 하나"를 알 방법이 없다.
    """
    response = client.post("/api/personas")

    assert response.status_code == 405
    assert response.headers.get("allow") is not None
    assert "GET" in response.headers["allow"]


def test_본문을_실을_수_없는_상태_코드에는_바디를_붙이지_않는다():
    """204 는 "본문 없음"이 정의 자체이고 304 는 캐시된 본문을 쓰라는 뜻이다.

    지금은 이 코드를 던지는 엔드포인트가 없지만, DELETE 를 추가하면서 204 를
    쓰는 순간 스펙 위반 응답이 나간다.
    """
    app = create_app()

    @app.get("/api/_no_content")
    def _no_content() -> None:
        raise StarletteHTTPException(status_code=204)

    with TestClient(app, raise_server_exceptions=False) as test_client:
        response = test_client.get("/api/_no_content")

    assert response.status_code == 204
    assert response.content == b""
