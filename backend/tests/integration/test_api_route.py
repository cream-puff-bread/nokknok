"""결제 라우팅 엔드포인트 통합 테스트.

실제 DB(카드 A/B/C 시드 + 생성된 페르소나 거래)에 붙는다. 거래 내역은
generate_persona.py로 만든 데이터라 정확한 할인액을 미리 알 수 없으므로,
숫자 자체보다 응답 형식·오류 매핑·필드 간 정합성을 검증한다.
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


def _route(client: TestClient, **overrides):
    body = {"personaId": 1, "amount": 100_000, "category": "ONLINE"}
    body.update(overrides)
    return client.post("/api/route", json=body)


class TestRouteHappyPath:
    def test_응답_형식이_계약_camelCase다(self, client: TestClient):
        response = _route(client)

        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"best", "alternatives", "newCardSuggestion", "computeMeta"}
        assert set(body["best"]) == {
            "cardId", "cardName", "payDate", "paymentType", "installmentMonths",
            "expectedDiscount", "perfAchieved", "perfCurrent", "perfRequired",
            "ruleId", "explanation", "clauses",
        }
        assert set(body["computeMeta"]) == {
            "candidatesTotal", "candidatesPruned", "elapsedMs", "excludedUnverifiedCards",
        }

    def test_explanation은_LLM_미연결로_null이다(self, client: TestClient):
        # CLAUDE.md: LLM 실패 시에도 계산 결과는 반드시 응답에 포함된다.
        # 지금은 LLM 연결 자체를 안 했으므로 항상 null이어야 한다.
        best = _route(client).json()["best"]
        assert best["explanation"] is None

    def test_alternatives에는_explanation_필드가_없다(self, client: TestClient):
        body = _route(client, personaId=2).json()
        if body["alternatives"]:
            assert "explanation" not in body["alternatives"][0]
            assert "clauses" not in body["alternatives"][0]

    def test_ruleId가_있으면_best_카드_소속_규칙이다(self, client: TestClient, db_session: Session):
        from sqlalchemy import text

        body = _route(client, personaId=2).json()
        rule_id = body["best"]["ruleId"]
        if rule_id is not None:
            row = db_session.execute(
                text("SELECT card_id FROM card_benefit_rule WHERE id = :rid"),
                {"rid": rule_id},
            ).first()
            assert row is not None
            assert row[0] == body["best"]["cardId"]

    def test_보유_카드_수만큼_후보_총계가_잡힌다(self, client: TestClient):
        # 페르소나 2(INSTALLMENT_HEAVY)는 카드 3장을 보유한다(personas.seed.sql).
        body = _route(client, personaId=2).json()
        assert body["computeMeta"]["candidatesTotal"] == 3


class TestRouteValidation:
    def test_없는_페르소나는_404(self, client: TestClient):
        response = _route(client, personaId=999999)

        assert response.status_code == 404
        assert response.json()["code"] == ErrorCode.PERSONA_NOT_FOUND

    def test_존재하지_않는_카테고리는_422(self, client: TestClient):
        response = _route(client, category="NOT_A_REAL_CATEGORY")

        assert response.status_code == 422
        assert response.json()["code"] == ErrorCode.INVALID_CATEGORY

    def test_금액이_0이면_422(self, client: TestClient):
        response = _route(client, amount=0)

        assert response.status_code == 422
        assert response.json()["code"] == ErrorCode.INVALID_AMOUNT

    def test_금액이_음수면_422(self, client: TestClient):
        response = _route(client, amount=-1000)

        assert response.status_code == 422
        assert response.json()["code"] == ErrorCode.INVALID_AMOUNT
