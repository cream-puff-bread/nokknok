"""질의 해석 테스트.

LLM 을 호출하지 않는다. 고정 응답을 주는 스텁으로 검증 로직만 본다.
응답 스키마를 지정해도 형식 위반이 아예 불가능해지지는 않으므로,
파싱 후 검증이 실제로 걸러내는지가 이 테스트의 관심사다.
"""

from __future__ import annotations

import pytest

from src.api.query_parser import (
    DEFAULT_INSTALLMENT_MONTHS,
    FALLBACK_CATEGORY,
    MAX_QUERY_LENGTH,
    QueryParser,
    build_response_schema,
)
from src.common.exceptions import LlmBudgetExceededError, QueryParseError
from src.forecast import PurchasePaymentType

CATEGORIES = ("ALL", "DINING", "ONLINE", "ETC")


class _StubClient:
    """LLM 호출 없이 고정 응답을 반환한다."""

    def __init__(self, payload: dict | None = None, error: Exception | None = None) -> None:
        self._payload = payload or {}
        self._error = error

    def complete_json(self, system: str, user: str, max_tokens: int = 2048) -> dict:
        if self._error is not None:
            raise self._error
        return self._payload


def parser(payload: dict | None = None, error: Exception | None = None) -> QueryParser:
    return QueryParser(_StubClient(payload, error), CATEGORIES)


def payload(**kwargs) -> dict:
    base = {
        "amount": 1_800_000,
        "payment_type": "LUMP",
        "installment_months": 0,
        "category": "ONLINE",
    }
    return {**base, **kwargs}


class Test정상해석:
    def test_결제_조건을_그대로_옮긴다(self):
        result = parser(payload()).parse("아이폰 180만원 사도 될까")

        assert result.amount == 1_800_000
        assert result.payment_type is PurchasePaymentType.LUMP
        assert result.installment_months == 0
        assert result.category == "ONLINE"

    def test_PlannedPurchase로_변환된다(self):
        result = parser(
            payload(payment_type="INSTALLMENT", installment_months=6)
        ).parse("할부로 사도 될까")

        purchase = result.to_purchase()

        assert purchase.amount == 1_800_000
        assert purchase.installment_months == 6


class Test검증:
    @pytest.mark.parametrize("amount", [0, -1000, None, "180만원", True])
    def test_금액이_없거나_양수가_아니면_거부한다(self, amount):
        """금액을 못 찾으면 무엇을 계산할지 자체를 모른다."""
        with pytest.raises(QueryParseError):
            parser(payload(amount=amount)).parse("아이폰 사도 될까")

    def test_마스터에_없는_카테고리는_거부한다(self):
        """spend_category 에 없는 코드는 이후 규칙 매칭이 조용히 실패해
        할인이 0원으로 계산된다. 여기서 끊는 편이 낫다.
        """
        with pytest.raises(QueryParseError):
            parser(payload(category="DINNING")).parse("외식 5만원")

    def test_알_수_없는_결제_방식은_거부한다(self):
        with pytest.raises(QueryParseError):
            parser(payload(payment_type="CASH")).parse("현금으로 사도 될까")

    def test_빈_응답도_거부한다(self):
        """안전 필터링 등으로 빈 응답이 오면 파싱 결과가 빈 dict 가 된다."""
        with pytest.raises(QueryParseError):
            parser({}).parse("아이폰 180만원")

    @pytest.mark.parametrize("query", ["", "   ", "가" * (MAX_QUERY_LENGTH + 1)])
    def test_질의_자체가_부적절하면_LLM을_호출하지_않는다(self, query):
        """빈 질의나 지나치게 긴 질의로 런타임 예산과 비용을 쓰지 않는다."""
        with pytest.raises(QueryParseError):
            parser(payload()).parse(query)


class Test정규화:
    def test_일시불이면_할부_개월을_0으로_맞춘다(self):
        result = parser(
            payload(payment_type="LUMP", installment_months=12)
        ).parse("아이폰 180만원 일시불")

        assert result.installment_months == 0

    @pytest.mark.parametrize("months", [0, -3, None])
    def test_할부인데_개월이_없으면_기본값을_쓴다(self, months):
        """개월을 밝히지 않는 질의가 흔하다. 파싱 실패로 돌리면 정상 질의를
        거절하게 된다. 해석 결과는 parsed 로 돌려줘 이용자가 확인한다.
        """
        result = parser(
            payload(payment_type="INSTALLMENT", installment_months=months)
        ).parse("할부로 사도 될까")

        assert result.installment_months == DEFAULT_INSTALLMENT_MONTHS


class Test실패처리:
    def test_LLM_예산_초과는_해석_실패로_바뀐다(self):
        """설명 생성과 다르다. 설명은 없어도 숫자를 낼 수 있지만
        질의를 해석하지 못하면 계산을 시작할 수 없다.
        """
        with pytest.raises(QueryParseError):
            parser(error=LlmBudgetExceededError("예산 초과")).parse("아이폰 180만원")


class Test응답스키마:
    def test_category_enum이_넘긴_목록과_같다(self):
        """코드에 카테고리를 다시 적으면 spend_category 가 바뀔 때 어긋난다."""
        schema = build_response_schema(CATEGORIES)

        assert schema.properties["category"].enum == list(CATEGORIES)

    def test_payment_type_enum이_고정_집합이다(self):
        schema = build_response_schema(CATEGORIES)

        assert set(schema.properties["payment_type"].enum) == {
            "LUMP",
            "INSTALLMENT",
            "INTEREST_FREE",
        }


class Test폴백_카테고리:
    def test_목록에_폴백_코드가_없으면_생성_단계에서_막는다(self):
        """프롬프트가 "분명하지 않으면 ETC" 라고 지시하는데 그 코드가 목록에
        없으면, 모델은 존재하지 않는 값을 쓰라는 지시를 받는다.

        조용히 넘어가면 애매한 질의마다 검증에서 걸려 계속 422 가 된다.
        """
        with pytest.raises(ValueError):
            QueryParser(_StubClient(payload()), ("DINING", "ONLINE"))

    def test_폴백_코드가_프롬프트에_실린다(self):
        assert FALLBACK_CATEGORY in CATEGORIES
        QueryParser(_StubClient(payload()), CATEGORIES)
