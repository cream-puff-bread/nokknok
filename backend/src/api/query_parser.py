"""자연어 질의에서 계산 파라미터를 뽑는다.

LLM 이 하는 일은 여기까지다 — "아이폰 180만원 할부로 사도 될까"에서
금액·결제 방식·할부 개월·카테고리를 뽑아낼 뿐, 잔고나 할인액은 계산하지
않는다. 계산은 전부 src/forecast/ 와 규칙 엔진이 한다.

## 실패 시 설명 생성과 다르게 처리하는 이유

설명 생성은 실패해도 explanation=null 로 두고 숫자를 낸다. 질의 파싱은
그럴 수 없다 — 무엇을 계산할지 자체를 모르므로 계산을 시작할 수 없다.
그래서 QueryParseError 를 던지고 호출부가 422 로 응답한다.

## 잘못 읽었을 때의 안전장치

"180만원"을 1,800,000 이 아니라 180 으로 읽어도 코드가 알아낼 방법은 없다.
5,000원짜리 결제도 정상 질의라 하한을 걸 수 없기 때문이다. 대신 해석 결과를
응답의 parsed 필드로 그대로 돌려준다. 이용자가 "180만원 일시불로 이해했습니다"를
눈으로 확인하고 틀렸으면 다시 묻는 것이 유일하게 확실한 검증이다.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from google.genai import types

from src.common.config import Settings, get_settings
from src.common.exceptions import LlmError, QueryParseError
from src.common.llm import LlmClient, build_provider, runtime_profile
from src.common.logging import get_logger
from src.forecast import PlannedPurchase, PurchasePaymentType

logger = get_logger(__name__)

# 할부 개월이 질의에 없을 때 쓰는 값. "할부로 사도 될까"처럼 개월을 밝히지
# 않는 질의가 흔한데(api-spec.yaml 의 예시 질의도 그렇다) 파싱 실패로 돌리면
# 정상 질의를 거절하게 된다. 국내 카드에서 무이자 구간으로 가장 흔한 12개월을
# 기본값으로 삼고, 해석 결과를 parsed 로 돌려줘 이용자가 확인하게 한다.
DEFAULT_INSTALLMENT_MONTHS = 12

# 무엇을 사는지 분명하지 않을 때 쓰는 카테고리. spend_category 마스터의 값이며,
# 프롬프트가 이 코드를 직접 지시하므로 목록에 실제로 있는지 생성 시점에 확인한다.
FALLBACK_CATEGORY = "ETC"

# 질의 길이 상한. 긴 문장을 그대로 보내면 런타임 예산을 넘기기 쉽고
# 비용도 는다. 화면 입력란도 같은 값으로 제한한다.
MAX_QUERY_LENGTH = 200

_PAYMENT_TYPES = tuple(t.value for t in PurchasePaymentType)

SYSTEM_PROMPT = """당신은 카드 이용자의 질문에서 결제 조건만 뽑아내는 도구다.

규칙:
- 금액은 원 단위 정수로 변환한다. "180만원"은 1800000 이다.
- 결제 방식은 {payment_types} 중 하나다. 명시가 없으면 LUMP 로 본다.
- 할부인데 개월 수가 없으면 {default_months} 를 쓴다. 일시불이면 0 이다.
- 카테고리는 다음 중 하나만 쓴다: {categories}
  무엇을 사는지 분명하지 않으면 {fallback} 을 쓴다.
- 금액을 찾을 수 없으면 amount 를 0 으로 둔다. 임의로 지어내지 않는다.
- 계산하지 않는다. 잔고나 할인액을 추정하지 않는다."""

USER_TEMPLATE = "다음 질문에서 결제 조건을 뽑아라.\n\n{query}"


@dataclass(frozen=True, slots=True)
class ParsedQuery:
    """contracts/api-spec.yaml 의 ParsedQuery 와 대응한다."""

    amount: int
    payment_type: PurchasePaymentType
    installment_months: int
    category: str

    def to_purchase(self) -> PlannedPurchase:
        return PlannedPurchase(
            amount=self.amount,
            payment_type=self.payment_type,
            installment_months=self.installment_months,
        )


def build_response_schema(categories: Sequence[str]) -> types.Schema:
    """모델이 임의 문자열을 낼 여지를 스키마 단계에서 없앤다.

    category 와 payment_type 은 값 집합이 고정이므로 enum 으로 못박는다.
    categories 는 spend_category 마스터를 조회해 넘긴다 — 코드에 목록을
    다시 적으면 마스터가 바뀔 때 조용히 어긋난다.
    """
    return types.Schema(
        type=types.Type.OBJECT,
        properties={
            "amount": types.Schema(type=types.Type.INTEGER),
            "payment_type": types.Schema(
                type=types.Type.STRING, enum=list(_PAYMENT_TYPES)
            ),
            "installment_months": types.Schema(type=types.Type.INTEGER),
            "category": types.Schema(type=types.Type.STRING, enum=list(categories)),
        },
        required=["amount", "payment_type", "installment_months", "category"],
    )


class QueryParser:
    def __init__(self, client: LlmClient, categories: Sequence[str]) -> None:
        self._client = client
        # 프롬프트에 적는 목록과 응답 스키마 enum 이 다르면 모델이 "쓰라고 한 값"과
        # "허용된 값"이 어긋난 채로 호출을 받는다. 같은 목록을 양쪽에 쓴다.
        self._categories = tuple(categories)
        if FALLBACK_CATEGORY not in self._categories:
            # 프롬프트가 "분명하지 않으면 ETC" 라고 지시하는데 그 코드가 목록에
            # 없으면, 모델은 존재하지 않는 값을 쓰라는 지시를 받는다. 조용히
            # 넘어가면 애매한 질의마다 검증에서 걸려 계속 422 가 된다.
            raise ValueError(
                f"카테고리 목록에 폴백 코드({FALLBACK_CATEGORY})가 없습니다"
            )

    def parse(self, query: str) -> ParsedQuery:
        query = query.strip()
        if not query:
            raise QueryParseError("질의가 비어 있습니다")
        if len(query) > MAX_QUERY_LENGTH:
            raise QueryParseError(f"질의가 너무 깁니다({len(query)}자)")

        system = SYSTEM_PROMPT.format(
            payment_types=", ".join(_PAYMENT_TYPES),
            default_months=DEFAULT_INSTALLMENT_MONTHS,
            fallback=FALLBACK_CATEGORY,
            categories=", ".join(self._categories),
        )

        try:
            payload = self._client.complete_json(
                system, USER_TEMPLATE.format(query=query), max_tokens=256
            )
        except LlmError as exc:
            # 예산 초과·인증 실패·네트워크 오류를 여기서 하나로 모은다.
            # 호출부는 "해석하지 못했다"만 알면 되고, 원인은 로그에 남는다.
            logger.warning("질의 해석 LLM 호출 실패: %s", type(exc).__name__)
            raise QueryParseError("LLM 호출에 실패했습니다") from exc

        return self._validate(payload)

    def _validate(self, payload: dict) -> ParsedQuery:
        """응답 스키마를 지정해도 형식 위반이 아예 불가능해지지는 않는다.

        스키마는 모델을 강하게 유도할 뿐이고, 안전 필터링 등으로 빈 응답이
        오면 파싱 단계에서 빈 dict 가 된다. 여기서 한 번 더 확인한다.
        """
        amount = payload.get("amount")
        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
            raise QueryParseError("금액을 찾지 못했습니다")

        raw_type = payload.get("payment_type")
        if raw_type not in _PAYMENT_TYPES:
            raise QueryParseError(f"알 수 없는 결제 방식입니다: {raw_type!r}")
        payment_type = PurchasePaymentType(raw_type)

        category = payload.get("category")
        if category not in self._categories:
            # spend_category 에 없는 코드가 들어오면 이후 규칙 매칭이 조용히
            # 실패해 할인이 0원으로 계산된다. 여기서 끊는 편이 낫다.
            raise QueryParseError(f"알 수 없는 카테고리입니다: {category!r}")

        months = payload.get("installment_months")
        if not isinstance(months, int) or isinstance(months, bool) or months < 0:
            months = 0
        if payment_type is PurchasePaymentType.LUMP:
            months = 0
        elif months <= 0:
            months = DEFAULT_INSTALLMENT_MONTHS

        logger.info(
            "질의 해석 완료 payment_type=%s months=%d category=%s",
            payment_type,
            months,
            category,
        )
        return ParsedQuery(
            amount=amount,
            payment_type=payment_type,
            installment_months=months,
            category=category,
        )


def build_query_parser(
    categories: Sequence[str], settings: Settings | None = None
) -> QueryParser:
    """런타임 프로파일로 파서를 만든다.

    배치 프로파일(5회 / 15초)을 쓰면 시연 중 화면이 1분 가까이 멈춘다.
    이 경로는 동기 응답이므로 총 예산 기준이어야 한다.
    """
    settings = settings or get_settings()
    provider = build_provider(settings, response_schema=build_response_schema(categories))
    client = LlmClient(runtime_profile(settings), provider=provider, settings=settings)
    return QueryParser(client, categories)
