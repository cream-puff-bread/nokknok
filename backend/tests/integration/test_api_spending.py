"""카테고리별 소비 집계 엔드포인트(/api/spending) 통합 테스트.

실제 DB에 붙어 시드 데이터로 검증한다. 기대값은 카테고리 우선순위나 예측처럼
계산이 섞이는 값이 아니라 transaction 원본을 그대로 합산한 값이라, 시드가
바뀌지 않는 한 고정된 숫자로 대조할 수 있다.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.api.deps import get_db_session
from src.api.errors import ErrorCode
from src.main import create_app

pytestmark = pytest.mark.integration


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client


def test_페르소나2_2026_08_카테고리별_합계가_기대값과_일치한다(client: TestClient):
    response = client.get("/api/spending", params={"personaId": 2, "month": "2026-08"})

    assert response.status_code == 200
    body = response.json()
    assert body["month"] == "2026-08"
    assert body["total"] == 1_018_690
    assert body["count"] == 38

    by_category = {c["category"]: (c["amount"], c["count"]) for c in body["categories"]}
    assert by_category == {
        "ONLINE": (307_950, 3),
        "DINING": (255_600, 10),
        "DELIVERY": (174_740, 7),
        "GROCERY": (118_170, 2),
        "TELECOM": (53_920, 1),
        "CAFE": (44_690, 7),
        "TRANSPORT": (42_040, 7),
        "CULTURE": (21_580, 1),
    }


def test_카테고리는_금액_내림차순이다(client: TestClient):
    body = client.get("/api/spending", params={"personaId": 2, "month": "2026-08"}).json()

    amounts = [c["amount"] for c in body["categories"]]
    assert amounts == sorted(amounts, reverse=True)


def test_카테고리_라벨은_마스터에서_온다(client: TestClient, db_session: Session):
    from sqlalchemy import text

    labels = dict(
        db_session.execute(text("SELECT code, label FROM spend_category")).all()
    )
    body = client.get("/api/spending", params={"personaId": 2, "month": "2026-08"}).json()

    for category in body["categories"]:
        assert category["categoryLabel"] == labels[category["category"]]


@pytest.mark.parametrize(
    ("persona_id", "expected_total", "expected_count"),
    [(1, 891_940, 31), (3, 1_534_180, 58)],
)
def test_다른_페르소나도_합계가_일치한다(
    client: TestClient, persona_id: int, expected_total: int, expected_count: int
):
    body = client.get(
        "/api/spending", params={"personaId": persona_id, "month": "2026-08"}
    ).json()

    assert body["total"] == expected_total
    assert body["count"] == expected_count


def test_month_생략시_거래가_있는_마지막_달을_고른다(client: TestClient):
    response = client.get("/api/spending", params={"personaId": 2})

    assert response.status_code == 200
    body = response.json()
    assert body["month"] == "2026-08"
    assert body["total"] == 1_018_690


def test_거래_없는_달은_빈_배열과_0을_200으로_돌려준다(client: TestClient):
    response = client.get("/api/spending", params={"personaId": 2, "month": "2026-09"})

    assert response.status_code == 200
    body = response.json()
    assert body["month"] == "2026-09"
    assert body["categories"] == []
    assert body["total"] == 0
    assert body["count"] == 0


def test_완결된_달의_monthEnd는_말일이다(client: TestClient):
    """2026-07은 세 페르소나 모두 7/31까지 거래가 있다(선행 조사로 확인)."""
    body = client.get("/api/spending", params={"personaId": 2, "month": "2026-07"}).json()

    assert body["monthEnd"] == "2026-07-31"


def test_미완결_달의_monthEnd는_말일보다_이르다(client: TestClient):
    body = client.get("/api/spending", params={"personaId": 2, "month": "2026-08"}).json()

    assert body["monthEnd"] == "2026-08-20"


def test_없는_페르소나는_404와_PERSONA_NOT_FOUND다(client: TestClient):
    response = client.get("/api/spending", params={"personaId": 999, "month": "2026-08"})

    assert response.status_code == 404
    assert response.json()["code"] == ErrorCode.PERSONA_NOT_FOUND


@pytest.mark.parametrize("bad_month", ["2026-8", "abc", "2026-13", "2026/08"])
def test_month_형식_오류는_422다(client: TestClient, bad_month: str):
    response = client.get("/api/spending", params={"personaId": 2, "month": bad_month})

    assert response.status_code == 422
    assert response.json()["code"] == ErrorCode.INVALID_REQUEST


def test_응답_키가_계약의_camelCase다(client: TestClient):
    body = client.get("/api/spending", params={"personaId": 2, "month": "2026-08"}).json()

    assert set(body) == {"month", "monthEnd", "total", "count", "categories"}
    assert set(body["categories"][0]) == {"category", "categoryLabel", "amount", "count"}
