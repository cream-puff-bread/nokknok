"""헬스체크 엔드포인트와 앱 조립 테스트.

DB도 네트워크도 없이 통과해야 한다. keep-alive 가 의존하는 경로이므로
설정이 비어 있는 환경(클론 직후, CI)에서도 200 이어야 한다.
"""

from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient

from src.common.config import Settings
from src.main import allowed_origins, create_app


def test_헬스체크가_200과_ok를_반환한다():
    # with 로 감싸야 lifespan(기동·종료 훅)까지 실제로 실행된다.
    with TestClient(create_app()) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    # api-spec.yaml 이 time 을 date-time 으로 규정한다. 파싱되지 않으면 계약 위반이다.
    datetime.fromisoformat(body["time"])


def test_헬스체크는_DB_설정_없이도_동작한다():
    """DATABASE_URL 이 비어 있어도 200 이어야 한다.

    DB 조회를 넣으면 인스턴스는 멀쩡한데도 keep-alive 가 실패로 보고한다.
    엔드포인트가 나중에 DB를 건드리기 시작하면 이 테스트가 잡아낸다.
    """
    settings = Settings(DATABASE_URL="", _env_file=None)  # type: ignore[call-arg]

    with TestClient(create_app(settings)) as client:
        assert client.get("/api/health").status_code == 200


def test_OpenAPI_문서에_헬스체크가_노출된다():
    """/docs 가 계약과 어긋나면 프론트가 잘못된 형식을 기준으로 작업하게 된다."""
    with TestClient(create_app()) as client:
        schema = client.get("/openapi.json").json()

    assert "/api/health" in schema["paths"]
    assert schema["info"]["version"] == "0.1.0"


def test_CORS_ORIGIN을_쉼표로_나눈다():
    """배포 시 Vercel 도메인과 로컬 주소를 동시에 허용해야 한다."""
    assert allowed_origins("http://localhost:5173") == ["http://localhost:5173"]
    assert allowed_origins("https://a.vercel.app, http://localhost:5173") == [
        "https://a.vercel.app",
        "http://localhost:5173",
    ]
    # 빈 값이 목록에 들어가면 모든 오리진을 허용하는 것처럼 보이는 항목이 생긴다.
    assert allowed_origins("") == []
    assert allowed_origins("http://localhost:5173, ") == ["http://localhost:5173"]
