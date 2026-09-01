"""보유 카드 현황 엔드포인트 통합 테스트.

이 화면의 실적은 결제 라우팅이 말하는 실적과 반드시 같아야 한다. 같은 값을
두 화면이 다르게 말하면 이용자가 어느 쪽을 믿어야 할지 알 수 없고, 그건 이
서비스가 존재하는 이유를 무너뜨린다. 그래서 두 응답을 직접 맞춰 본다.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
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


def _cards(client: TestClient, persona_id: int = 2):
    return client.get(f"/api/cards?personaId={persona_id}").json()


def test_응답_키가_계약의_camelCase다(client: TestClient):
    card = _cards(client)[0]

    assert set(card) == {
        "cardId", "cardName", "issuer", "isDemo", "paymentDay",
        "perfPeriodStart", "perfPeriodEnd", "perfCurrent", "perfNextThreshold",
        "monthlyCap", "benefits", "exclusions",
    }
    assert set(card["benefits"][0]) == {
        "category", "categoryLabel", "perfMin", "perfMax",
        "discountRate", "categoryCap", "active",
    }


def test_보유한_카드만_나온다(client: TestClient, db_session: Session):
    rows = db_session.execute(
        text("SELECT card_id FROM persona_card WHERE persona_id = 2")
    ).all()
    owned = {r[0] for r in rows}

    assert {c["cardId"] for c in _cards(client)} == owned


def test_실적이_결제_라우팅과_같다(client: TestClient):
    """두 화면이 같은 숫자를 말해야 한다 — 이 테스트가 이 파일의 핵심이다."""
    by_card = {c["cardId"]: c["perfCurrent"] for c in _cards(client)}

    route = client.post(
        "/api/route", json={"personaId": 2, "amount": 100_000, "category": "ONLINE"}
    ).json()

    for candidate in [route["best"], *route["alternatives"]]:
        assert candidate["perfCurrent"] == by_card[candidate["cardId"]], (
            f"카드 {candidate['cardId']} 의 실적이 두 화면에서 다르다"
        )


def test_검수_전_규칙은_보여주지_않는다(client: TestClient, db_session: Session):
    """받을 수 없는 혜택을 약속하지 않는다."""
    unverified = db_session.execute(
        text("SELECT count(*) FROM card_benefit_rule WHERE verified = false")
    ).scalar_one()
    shown = sum(len(c["benefits"]) for c in _cards(client))
    verified = db_session.execute(
        text(
            "SELECT count(*) FROM card_benefit_rule r"
            " JOIN persona_card pc ON pc.card_id = r.card_id"
            " WHERE pc.persona_id = 2 AND r.verified = true"
        )
    ).scalar_one()

    assert shown == verified
    assert unverified >= 0  # 시드에 미검수 행이 없더라도 위 등식은 성립해야 한다


def test_active는_지금_실적_구간과_일치한다(client: TestClient):
    for card in _cards(client):
        perf = card["perfCurrent"]
        for b in card["benefits"]:
            expected = b["perfMin"] <= perf and (
                b["perfMax"] is None or perf < b["perfMax"]
            )
            assert b["active"] is expected


def test_실적이_모자라면_다음_문턱을_알려준다(client: TestClient):
    for card in _cards(client):
        if not card["benefits"]:
            continue
        assert card["perfNextThreshold"] == min(b["perfMin"] for b in card["benefits"])


def test_카테고리_라벨이_마스터를_따른다(client: TestClient, db_session: Session):
    rows = db_session.execute(text("SELECT code, label FROM spend_category")).all()
    master = {r[0]: r[1] for r in rows}

    for card in _cards(client):
        for b in card["benefits"]:
            assert b["categoryLabel"] == master[b["category"]]


def test_제외_항목이_사람이_읽는_이름으로_나온다(client: TestClient):
    labels = {
        e["targetLabel"]
        for card in _cards(client)
        for e in card["exclusions"]
        if e["targetKind"] == "PAYMENT_TYPE"
    }

    assert "무이자 할부" in labels


def test_없는_페르소나는_404다(client: TestClient):
    response = client.get("/api/cards?personaId=999")

    assert response.status_code == 404
    assert response.json()["code"] == ErrorCode.PERSONA_NOT_FOUND
