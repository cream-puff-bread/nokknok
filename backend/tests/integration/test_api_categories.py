"""카테고리 목록 엔드포인트 통합 테스트.

이 엔드포인트의 존재 이유는 화면이 카테고리 코드를 하드코딩하지 않게 하는
것이므로, 검증의 초점도 "코드가 지어낸 목록이 아니라 마스터 그대로인가"에
둔다. 목록이 마스터와 어긋나면 화면 선택지가 서버 검증을 통과하지 못한다.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.api.deps import get_db_session
from src.main import create_app
from src.repository.category import WILDCARD_CATEGORY

pytestmark = pytest.mark.integration


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client


def test_목록이_마스터에서_ALL만_뺀_것과_같다(client: TestClient, db_session: Session):
    rows = db_session.execute(text("SELECT code FROM spend_category")).all()
    expected = {r[0] for r in rows} - {WILDCARD_CATEGORY}

    body = client.get("/api/categories").json()

    assert {c["code"] for c in body} == expected


def test_와일드카드는_선택지에_없다(client: TestClient):
    # ALL 이 화면 선택지에 뜨면 이용자가 그걸 고를 수 있고, 그러면
    # "카테고리 전용 규칙이 ALL 보다 우선한다"는 규칙 자체가 무의미해진다.
    codes = [c["code"] for c in client.get("/api/categories").json()]

    assert WILDCARD_CATEGORY not in codes


def test_마스터의_sort_no_순서를_유지한다(client: TestClient, db_session: Session):
    rows = db_session.execute(
        text("SELECT code FROM spend_category ORDER BY sort_no")
    ).all()
    expected = [r[0] for r in rows if r[0] != WILDCARD_CATEGORY]

    codes = [c["code"] for c in client.get("/api/categories").json()]

    assert codes == expected


def test_라벨이_비어있지_않다(client: TestClient):
    # 라벨이 비면 화면 드롭다운이 빈 항목으로 그려진다.
    body = client.get("/api/categories").json()

    assert body
    assert all(c["label"].strip() for c in body)


def test_응답에_선택지로_고른_값이_라우팅_검증을_통과한다(client: TestClient):
    """목록과 검증이 같은 원천을 쓰는지 확인한다.

    이 둘이 어긋나면 화면이 제시한 선택지를 골랐는데 INVALID_CATEGORY 가
    돌아온다 — 엔드포인트를 만든 이유가 사라지는 실패 방식이다.
    """
    codes = [c["code"] for c in client.get("/api/categories").json()]

    for code in codes:
        res = client.post(
            "/api/route", json={"personaId": 1, "amount": 50_000, "category": code}
        )
        assert res.json().get("code") != "INVALID_CATEGORY", (
            f"목록이 제시한 {code} 를 라우팅이 거부했다"
        )
