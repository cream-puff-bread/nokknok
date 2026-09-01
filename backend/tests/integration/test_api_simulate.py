"""/api/simulate 통합 테스트.

LLM 은 호출하지 않는다. 질의 해석기를 의존성 오버라이드로 갈아끼워
조립·응답 형식·오류 경로만 본다. 해석 로직 자체는 test_query_parser.py 가
스텁으로 검증한다.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.api.deps import get_db_session, get_query_parser
from src.api.errors import ErrorCode
from src.api.query_parser import ParsedQuery
from src.common.exceptions import QueryParseError
from src.forecast import PurchasePaymentType
from src.main import create_app

pytestmark = pytest.mark.integration


class _StubParser:
    def __init__(self, parsed: ParsedQuery | None = None, error: Exception | None = None) -> None:
        self._parsed = parsed
        self._error = error

    def parse(self, query: str) -> ParsedQuery:
        if self._error is not None:
            raise self._error
        assert self._parsed is not None
        return self._parsed


def _parsed(**kwargs) -> ParsedQuery:
    base = {
        "amount": 1_800_000,
        "payment_type": PurchasePaymentType.INSTALLMENT,
        "installment_months": 12,
        "category": "ONLINE",
    }
    return ParsedQuery(**{**base, **kwargs})


@pytest.fixture
def make_client(db_session: Session):
    def _make(parser) -> Iterator[TestClient]:
        app = create_app()
        app.dependency_overrides[get_db_session] = lambda: db_session
        app.dependency_overrides[get_query_parser] = lambda: parser
        return TestClient(app)

    return _make


@pytest.fixture
def client(make_client):
    return make_client(_StubParser(_parsed()))


def test_응답이_계약_형식을_따른다(client: TestClient):
    response = client.post("/api/simulate", json={"personaId": 2, "query": "아이폰 180만원 할부"})

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"parsed", "scenarios", "deadPoint", "forecastMeta"}
    assert set(body["parsed"]) == {
        "amount",
        "paymentType",
        "installmentMonths",
        "category",
    }
    assert set(body["forecastMeta"]) == {"monthsUsed", "txnCount", "coldStart"}


def test_해석_결과를_그대로_돌려준다(client: TestClient):
    """이용자가 "180만원 12개월 할부로 이해했습니다"를 눈으로 확인해야 한다.

    금액을 잘못 읽어도 코드가 알아낼 방법이 없어, 이 필드가 유일한 검증 수단이다.
    """
    parsed = client.post(
        "/api/simulate", json={"personaId": 2, "query": "아이폰 180만원 할부"}
    ).json()["parsed"]

    assert parsed["amount"] == 1_800_000
    assert parsed["paymentType"] == "INSTALLMENT"
    assert parsed["installmentMonths"] == 12


def test_시나리오_세_개가_각각_여섯_달을_담는다(client: TestClient):
    body = client.post("/api/simulate", json={"personaId": 2, "query": "아이폰 180만원"}).json()

    levels = [s["level"] for s in body["scenarios"]]
    assert levels == ["COMFORTABLE", "NORMAL", "TIGHT"]
    for scenario in body["scenarios"]:
        assert len(scenario["points"]) == 6
        assert set(scenario["points"][0]) == {"month", "balance"}


def test_예측_근거가_함께_실린다(client: TestClient):
    """숫자만 보여주고 근거를 감추면 표본이 한 달뿐일 때도 같은 확신으로 보인다."""
    meta = client.post(
        "/api/simulate", json={"personaId": 2, "query": "아이폰 180만원"}
    ).json()["forecastMeta"]

    assert meta["monthsUsed"] >= 1
    assert meta["txnCount"] > 0
    assert meta["coldStart"] is False


def test_큰_지출은_잔고를_더_끌어내린다(make_client):
    """검토 중인 지출이 실제로 추이에 반영되는지 본다."""

    def last_balance(amount: int) -> int:
        client = make_client(_StubParser(_parsed(amount=amount)))
        body = client.post("/api/simulate", json={"personaId": 3, "query": "질의"}).json()
        return body["scenarios"][1]["points"][-1]["balance"]

    assert last_balance(6_000_000) < last_balance(600_000)


def test_해석_실패는_422_QUERY_PARSE_FAILED다(make_client):
    client = make_client(_StubParser(error=QueryParseError("금액을 찾지 못했습니다")))

    response = client.post("/api/simulate", json={"personaId": 2, "query": "사도 될까"})

    assert response.status_code == 422
    assert response.json()["code"] == ErrorCode.QUERY_PARSE_FAILED


def test_없는_페르소나는_404다(client: TestClient):
    response = client.post("/api/simulate", json={"personaId": 999999, "query": "아이폰"})

    assert response.status_code == 404
    assert response.json()["code"] == ErrorCode.PERSONA_NOT_FOUND


@pytest.mark.parametrize(
    "body",
    [
        {"personaId": 2},
        {"personaId": 2, "query": ""},
        {"personaId": 2, "query": "가" * 500},
        {"query": "아이폰 180만원"},
    ],
)
def test_요청_형식_오류는_422_INVALID_REQUEST다(client: TestClient, body):
    response = client.post("/api/simulate", json=body)

    assert response.status_code == 422
    assert response.json()["code"] == ErrorCode.INVALID_REQUEST


class _ExplodingParser:
    """호출되면 실패한다. 구조화 입력이 파서를 건드리지 않는지 확인하는 용도."""

    def parse(self, query: str) -> ParsedQuery:
        raise AssertionError("구조화 입력인데 질의 해석기가 호출됐다")


_PURCHASE = {
    "amount": 1_800_000,
    "paymentType": "INSTALLMENT",
    "installmentMonths": 6,
    "category": "ONLINE",
}


class TestStructuredPurchase:
    """결제 라우팅에서 넘어오는 구조화 입력.

    그 화면은 금액·카테고리·결제 방식을 이미 정확히 알고 있다. 문장으로
    만들어 LLM 에 되읽히면 시간을 더 쓰고, 해석이 어긋나면 두 화면이 서로
    다른 숫자를 말하게 된다.
    """

    def test_구조화_입력은_질의_해석기를_호출하지_않는다(self, make_client):
        client = make_client(_ExplodingParser())

        response = client.post(
            "/api/simulate", json={"personaId": 2, "purchase": _PURCHASE}
        )

        assert response.status_code == 200

    def test_넘긴_값이_parsed로_그대로_돌아온다(self, make_client):
        client = make_client(_ExplodingParser())

        body = client.post(
            "/api/simulate", json={"personaId": 2, "purchase": _PURCHASE}
        ).json()

        assert body["parsed"] == _PURCHASE

    def test_purchase가_query보다_우선한다(self, make_client):
        # 둘 다 오면 해석기를 타지 않는다 — 탔다면 _ExplodingParser 가 터진다.
        client = make_client(_ExplodingParser())

        body = client.post(
            "/api/simulate",
            json={"personaId": 2, "query": "전혀 다른 질문", "purchase": _PURCHASE},
        ).json()

        assert body["parsed"] == _PURCHASE

    def test_같은_구매면_자연어와_결과가_같다(self, make_client):
        parsed = _parsed(installment_months=6)
        natural = make_client(_StubParser(parsed)).post(
            "/api/simulate", json={"personaId": 2, "query": "아이폰 180만원 6개월 할부"}
        ).json()

        structured = make_client(_ExplodingParser()).post(
            "/api/simulate", json={"personaId": 2, "purchase": _PURCHASE}
        ).json()

        assert structured["scenarios"] == natural["scenarios"]
        assert structured["deadPoint"] == natural["deadPoint"]

    def test_둘_다_없으면_422다(self, client: TestClient):
        response = client.post("/api/simulate", json={"personaId": 2})

        assert response.status_code == 422
        assert response.json()["code"] == ErrorCode.INVALID_REQUEST

    def test_마스터에_없는_카테고리는_거부한다(self, make_client):
        """LLM 을 건너뛰어도 값 검증까지 건너뛰지는 않는다."""
        client = make_client(_ExplodingParser())

        response = client.post(
            "/api/simulate",
            json={"personaId": 2, "purchase": {**_PURCHASE, "category": "온라인"}},
        )

        assert response.status_code == 422
        assert response.json()["code"] == ErrorCode.INVALID_CATEGORY

    def test_금액이_0이면_거부한다(self, make_client):
        client = make_client(_ExplodingParser())

        response = client.post(
            "/api/simulate", json={"personaId": 2, "purchase": {**_PURCHASE, "amount": 0}}
        )

        assert response.status_code == 422
        assert response.json()["code"] == ErrorCode.INVALID_AMOUNT

    def test_결제방식과_할부개월이_어긋나면_거부한다(self, make_client):
        """PlannedPurchase 도 같은 불변식을 지키지만 거긴 ValueError 라 500 이 된다."""
        client = make_client(_ExplodingParser())

        lump = client.post(
            "/api/simulate",
            json={"personaId": 2, "purchase": {**_PURCHASE, "paymentType": "LUMP"}},
        )
        zero = client.post(
            "/api/simulate",
            json={"personaId": 2, "purchase": {**_PURCHASE, "installmentMonths": 0}},
        )

        assert lump.status_code == 422
        assert zero.status_code == 422
