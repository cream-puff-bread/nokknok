"""페르소나·가용잔고 엔드포인트 통합 테스트.

실제 DB에 붙어 시드 데이터로 검증한다. 세션은 conftest 의 db_session 을
주입해 테스트가 끝나면 롤백되게 하고, API 가 별도 커넥션을 열지 않도록 한다.
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


def test_페르소나_목록이_시드와_일치한다(client: TestClient):
    response = client.get("/api/personas")

    assert response.status_code == 200
    personas = response.json()
    assert [p["code"] for p in personas] == [
        "SUBSCRIPTION_HEAVY",
        "INSTALLMENT_HEAVY",
        "STABLE",
    ]


def test_페르소나_응답_키가_계약의_camelCase다(client: TestClient):
    """contracts/types.ts 의 Persona 와 필드명이 어긋나면 프론트가 undefined 를 그린다."""
    persona = client.get("/api/personas").json()[0]

    assert set(persona) == {
        "id",
        "code",
        "displayName",
        "description",
        "accountBalance",
        "cardCount",
    }


def test_cardCount가_보유_카드_수와_같다(client: TestClient):
    """persona_card 조인 결과다. 카드가 없는 페르소나도 0 으로 나와야 한다."""
    by_code = {p["code"]: p for p in client.get("/api/personas").json()}

    assert by_code["SUBSCRIPTION_HEAVY"]["cardCount"] == 2
    assert by_code["INSTALLMENT_HEAVY"]["cardCount"] == 3
    assert by_code["STABLE"]["cardCount"] == 3


def test_가용잔고는_통장잔액에서_확정지출을_뺀_값이다(client: TestClient):
    response = client.get("/api/balance", params={"personaId": 1})

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "accountBalance",
        "fixedTotal",
        "availableBalance",
        "fixedExpenses",
    }
    # 금액 계산은 서버가 전담한다. 프론트가 재계산하지 않아도 되도록
    # 세 값이 서로 맞아떨어져야 한다.
    assert body["availableBalance"] == body["accountBalance"] - body["fixedTotal"]
    assert body["fixedTotal"] == sum(e["amount"] for e in body["fixedExpenses"])


def test_확정지출_항목이_계약_형식을_따른다(client: TestClient):
    expense = client.get("/api/balance", params={"personaId": 1}).json()["fixedExpenses"][0]

    assert set(expense) == {
        "label",
        "amount",
        "chargeDay",
        "expenseType",
        "unusedSuspect",
    }
    assert expense["expenseType"] in {
        "SUBSCRIPTION",
        "INSTALLMENT",
        "LOAN",
        "INSURANCE",
    }


def test_미사용_의심_구독이_표시된다(client: TestClient):
    """구독 과다형 페르소나에는 last_used_date 가 오래된 구독이 섞여 있다.

    이 플래그가 항상 false 로 나오면 화면의 해지 권유 기능이 빈 채로 남는다.
    """
    expenses = client.get("/api/balance", params={"personaId": 1}).json()["fixedExpenses"]

    assert any(e["unusedSuspect"] for e in expenses)
    # 구독이 아닌 항목은 판정 대상이 아니다.
    assert all(
        not e["unusedSuspect"] for e in expenses if e["expenseType"] != "SUBSCRIPTION"
    )


def test_없는_페르소나는_404와_PERSONA_NOT_FOUND다(client: TestClient):
    response = client.get("/api/balance", params={"personaId": 999999})

    assert response.status_code == 404
    assert response.json()["code"] == ErrorCode.PERSONA_NOT_FOUND


def test_질의_카테고리_목록에서_와일드카드를_뺀다(db_session):
    """spend_category 의 ALL 은 소비 카테고리가 아니라 규칙 매칭용 폴백이다.

    거래·질의 카테고리로 새어 나가면 "카테고리 전용 규칙이 ALL 보다 우선한다"는
    우선순위 규칙이 의미를 잃는다. 거래 자체가 ALL 이 되어 무엇이 전용이고
    무엇이 폴백인지 구분할 수 없게 된다.
    """
    from src.repository.category import (
        WILDCARD_CATEGORY,
        list_category_codes,
        list_purchase_category_codes,
    )

    every = list_category_codes(db_session)
    purchasable = list_purchase_category_codes(db_session)

    assert WILDCARD_CATEGORY in every
    assert WILDCARD_CATEGORY not in purchasable
    assert set(purchasable) == set(every) - {WILDCARD_CATEGORY}
