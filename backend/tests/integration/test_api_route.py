"""결제 라우팅 엔드포인트 통합 테스트.

실제 DB(카드 A/B/C 시드 + 생성된 페르소나 거래)에 붙는다. 거래 내역은
generate_persona.py로 만든 데이터라 정확한 할인액을 미리 알 수 없으므로,
숫자 자체보다 응답 형식·오류 매핑·필드 간 정합성을 검증한다.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.api.deps import get_db_session, get_explanation_client
from src.api.errors import ErrorCode
from src.common.exceptions import LlmBudgetExceededError
from src.main import create_app

pytestmark = pytest.mark.integration


class _StubLlm:
    """LLM 호출 없이 고정된 결과를 낸다(tests/test_rag.py 의 _StubClient 와 같은 목적)."""

    def __init__(self, *, text: str | None = None, error: Exception | None = None) -> None:
        self._text = text
        self._error = error
        self.calls = 0

    def complete(self, system: str, user: str, max_tokens: int = 2048) -> str:
        self.calls += 1
        if self._error is not None:
            raise self._error
        assert self._text is not None
        return self._text


@contextmanager
def _client(db_session: Session, llm: object | None) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: db_session
    app.dependency_overrides[get_explanation_client] = lambda: llm
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    """기본값은 LLM 없음이다.

    이 파일의 검증 대상은 응답 형식·오류 매핑·필드 정합성이지 설명 생성이
    아니다. 실제 LLM 을 태우면 테스트가 네트워크 지연에 좌우되고 — 런타임
    예산이 총 경과 시간 기준이라 응답이 느린 날에는 explanation 이 null 이
    되어 결과가 실행할 때마다 달라진다 — 시연에 쓸 호출 예산도 갉아먹는다.
    """
    with _client(db_session, None) as test_client:
        yield test_client


@pytest.fixture
def client_with_llm(db_session: Session):
    """스텁 LLM 을 끼운 클라이언트를 만든다."""

    def make(llm: object) -> Iterator[TestClient]:
        return _client(db_session, llm)

    return make


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
            "cardId", "cardName", "isDemo", "payDate", "paymentType", "installmentMonths",
            "expectedDiscount", "perfAchieved", "perfCurrent", "perfRequired",
            "ruleId", "explanation", "clauses",
        }
        assert set(body["computeMeta"]) == {
            "candidatesTotal", "candidatesPruned", "elapsedMs", "excludedUnverifiedCards",
        }

    def test_LLM_클라이언트가_없으면_explanation은_null이다(self, client: TestClient):
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

    def test_dueDate_생략시_기본_30일_창이_적용된다(self, client: TestClient):
        # 페르소나 2(INSTALLMENT_HEAVY)는 카드 A/B/C를 보유한다(personas.seed.sql).
        # api-spec.yaml: dueDate "생략 시 오늘부터 30일" — 이 기본값을
        # API 계층(route.py)이 실제로 적용하는지 확인한다. 안 그러면
        # dueDate를 안 보내는 화면에서는 결제일 조합 탐색이 영영 안 켜진다
        # (하영님 리뷰, 2026-08-31).
        #
        # 30일 창이면 카드 3장 전부 결제일 조합(오늘/마감일 다음날)이 다
        # 생긴다. 무이자 할부가 BOTH 제외(실적·할인 모두)인 카드 A·B는
        # 일시불만 시도해 날짜 2개씩(가지치기 각 2개), PERFORMANCE만
        # 제외라 할인이 살아있는 카드 C는 날짜 2개 x 결제방식 2개=4개
        # (가지치기 없음): 2+2+4=8, 가지치기 2+2=4.
        body = _route(client, personaId=2).json()

        assert body["computeMeta"]["candidatesTotal"] == 8
        assert body["computeMeta"]["candidatesPruned"] == 4

    def test_dueDate를_짧게_주면_결제일_조합이_줄어든다(self, client: TestClient):
        # dueDate를 오늘로 좁히면 "미룬 후보" 자체가 만들어지지 않아
        # 카드당 결제방식 개수만큼만 시도된다 — 기본 30일 창과 대비되는
        # 경계 동작을 확인한다.
        today = date.today().isoformat()
        body = _route(client, personaId=2, dueDate=today).json()

        assert body["computeMeta"]["candidatesTotal"] == 4
        assert body["computeMeta"]["candidatesPruned"] == 2


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


class TestDemoBadge:
    """시연용 카드 표시.

    카탈로그의 카드가 전부 가상 상품인데 화면이 그걸 알 방법이 없으면,
    실제 할인액과 약관 인용이 붙은 추천을 실존 상품으로 오해할 수 있다
    (schema.sql: "화면에도 명시해야 한다", ui-system.md 뱃지 규칙).
    """

    def test_후보에_isDemo가_실려온다(self, client):
        body = client.post(
            "/api/route", json={"personaId": 1, "amount": 100_000, "category": "ONLINE"}
        ).json()

        assert "isDemo" in body["best"]
        assert all("isDemo" in a for a in body["alternatives"])

    def test_isDemo가_카드_마스터의_값과_같다(self, client, db_session):
        from sqlalchemy import text

        body = client.post(
            "/api/route", json={"personaId": 1, "amount": 100_000, "category": "ONLINE"}
        ).json()

        rows = db_session.execute(text("SELECT id, is_demo FROM card")).all()
        expected = {r[0]: r[1] for r in rows}

        for candidate in [body["best"], *body["alternatives"]]:
            assert candidate["isDemo"] == expected[candidate["cardId"]]


class TestExplanationFallback:
    """LLM 이 실패해도 계산 결과는 그대로 나간다.

    CLAUDE.md 의 핵심 불변식이다. 예전에는 이 경로를 "LLM_API_KEY 가 비어
    있어서 우연히 null" 인 상태로만 확인했는데, 그건 불변식이 지켜지는지가
    아니라 키가 없다는 사실만 확인하는 것이었다. 실제로 호출이 실패하는
    상황을 주입해서 검증한다.
    """

    def test_LLM이_실패해도_계산_결과는_그대로_응답된다(self, client_with_llm):
        stub = _StubLlm(error=LlmBudgetExceededError("런타임 예산 초과"))

        with client_with_llm(stub) as client:
            response = _route(client)

        assert response.status_code == 200
        best = response.json()["best"]
        assert stub.calls == 1, "설명 생성을 시도조차 하지 않았다"
        assert best["explanation"] is None
        # 설명이 빠졌다고 숫자까지 사라지면 안 된다.
        assert best["cardId"] > 0
        assert best["cardName"]
        assert isinstance(best["expectedDiscount"], int)
        assert isinstance(best["perfAchieved"], bool)

    def test_설명이_생성되면_그대로_실린다(self, client_with_llm):
        stub = _StubLlm(text="  이 카드가 가장 유리합니다.  ")

        with client_with_llm(stub) as client:
            best = _route(client).json()["best"]

        assert best["explanation"] == "이 카드가 가장 유리합니다."

    def test_빈_설명은_null로_바뀐다(self, client_with_llm):
        # 공백만 돌아왔는데 그대로 실으면 화면에 빈 설명 상자가 그려진다.
        stub = _StubLlm(text="   ")

        with client_with_llm(stub) as client:
            best = _route(client).json()["best"]

        assert best["explanation"] is None
