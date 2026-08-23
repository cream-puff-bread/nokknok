"""오류 응답 형식 테스트.

DB 없이 돈다. 세션 의존성은 오버라이드해 실제 연결을 만들지 않는다.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.deps import get_db_session
from src.api.errors import ErrorCode
from src.common.exceptions import PersonaNotFoundError
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
