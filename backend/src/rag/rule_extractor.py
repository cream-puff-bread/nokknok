"""조항에서 규칙을 추출한다.

LLM의 유일한 역할은 자연어 약관을 판정 가능한 조건식으로 옮기는 것이다.
금액 계산은 하지 않는다. 추출된 규칙은 검수를 거쳐야 운영에 반영된다.

프롬프트 설계에서 중요한 세 가지:

1. 카테고리 코드를 목록으로 못박는다. 자유롭게 두면 'FOOD' 같은 값을
   만들어내고 FK 제약에 걸린다.
2. 실적 제외와 할인 제외를 구분하도록 명시한다. 이 차이를 뭉개면
   엔진이 실적을 잘못 계산한다.
3. 규칙이 없으면 빈 배열을 반환하라고 지시한다. 억지로 만들어내면
   존재하지 않는 혜택이 DB에 들어간다.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

from src.common.exceptions import LlmError, RuleValidationError
from src.common.llm import LlmClient
from src.common.logging import get_logger
from src.rag.models import (
    BenefitRule,
    Clause,
    ExclusionRule,
    ExclusionType,
    ExtractionResult,
    TargetKind,
    VALID_CATEGORIES,
)

logger = get_logger(__name__)


SYSTEM_PROMPT = """\
당신은 신용카드 약관을 기계가 판정할 수 있는 규칙으로 옮기는 작업을 합니다.

주어진 약관 조항에서 아래 두 종류의 규칙만 추출하세요.

1. 혜택 규칙(benefit_rules) — 전월실적 구간별 할인율과 한도
2. 제외 규칙(exclusion_rules) — 실적 또는 할인에서 빠지는 항목

반드시 지킬 것:

- JSON 객체만 출력하세요. 설명, 인사말, 코드 펜스를 붙이지 마세요.
- 조항에 명시되지 않은 값을 추측해 채우지 마세요. 모르면 null 을 쓰세요.
- 규칙이 없는 조항이면 두 배열을 모두 빈 배열로 두세요.
- category 는 아래 목록의 값만 사용하세요. 목록에 없으면 ETC 를 쓰세요.
  {categories}
- discount_rate 는 비율입니다. 5% 는 0.05 로 쓰세요.
- 금액은 원 단위 정수입니다. "30만원"은 300000 입니다.
- exclusion_type 은 셋 중 하나입니다.
  PERFORMANCE: 전월실적 산정에서만 제외
  DISCOUNT: 할인 적용에서만 제외
  BOTH: 둘 다 제외
  실적과 할인은 다른 개념입니다. 조항이 어느 쪽을 말하는지 구분하세요.
- target_kind 는 CATEGORY, MERCHANT, PAYMENT_TYPE 중 하나입니다.
  PAYMENT_TYPE 일 때 target_value 는 LUMP, INSTALLMENT, INTEREST_FREE 중 하나입니다.

출력 형식:

{{
  "benefit_rules": [
    {{
      "perf_min": 300000,
      "perf_max": 500000,
      "category": "DINING",
      "discount_rate": 0.05,
      "category_cap": 10000
    }}
  ],
  "exclusion_rules": [
    {{
      "exclusion_type": "PERFORMANCE",
      "target_kind": "CATEGORY",
      "target_value": "TAX"
    }}
  ]
}}

perf_max 가 상한 없음이면 null 을 쓰세요.
category_cap 이 명시되지 않았으면 null 을 쓰세요.
"""


USER_TEMPLATE = """\
카드사: {issuer}
카드명: {card_name}

[약관 조항]
{content}
"""


class RuleExtractor:
    """조항 하나를 받아 규칙을 뽑는다.

    1단계 파이프라인이므로 조항과 규칙이 항상 짝을 이룬 채로 반환된다.
    호출부는 이 결과를 그대로 적재하면 clause_id 연결이 끝난다.
    """

    def __init__(
        self, client: LlmClient, categories: Sequence[str] | None = None
    ) -> None:
        self._client = client
        # 프롬프트 문구와 Gemini responseSchema의 enum이 서로 다른 목록을
        # 참조하면 모델이 "쓰라고 한 값"과 "허용된 값"이 어긋난 채로 호출을
        # 받는다. 스키마를 만들 때 쓴 것과 같은 목록을 여기서도 써야 한다.
        # 지정하지 않으면(스텁 client를 쓰는 단위 테스트 등) 기존처럼
        # VALID_CATEGORIES로 동작한다.
        self._categories = (
            tuple(categories) if categories is not None else tuple(sorted(VALID_CATEGORIES))
        )

    def extract(
        self, clause: Clause, issuer: str, card_name: str
    ) -> ExtractionResult:
        """조항에서 규칙을 추출한다.

        LLM 호출 실패는 예외로 올려보내 호출부가 재개 목록을 관리하게 한다.
        응답 형식 오류는 빈 결과로 처리한다. 한 조항 때문에 배치 전체가
        멈추면 안 되기 때문이다.
        """
        system = SYSTEM_PROMPT.format(categories=", ".join(self._categories))
        user = USER_TEMPLATE.format(
            issuer=issuer, card_name=card_name, content=clause.content
        )

        payload = self._client.complete_json(system, user)
        return self.build_result(clause, payload)

    def build_result(
        self, clause: Clause, payload: dict[str, Any]
    ) -> ExtractionResult:
        """LLM 응답(또는 캐시된 동일 구조)을 추출 결과로 변환한다.

        캐시 재사용 경로에서도 같은 검증을 거치도록 공개 메서드로 둔다.
        """
        result = ExtractionResult(clause=clause)

        for raw in payload.get("benefit_rules") or []:
            rule = self._parse_benefit(raw)
            if rule is not None:
                result.benefit_rules.append(rule)

        for raw in payload.get("exclusion_rules") or []:
            rule = self._parse_exclusion(raw)
            if rule is not None:
                result.exclusion_rules.append(rule)

        return result

    # ---------- internal ----------
    def _parse_benefit(self, raw: Any) -> BenefitRule | None:
        if not isinstance(raw, dict):
            return None
        try:
            rule = BenefitRule(
                perf_min=_to_int(raw.get("perf_min"), default=0),
                perf_max=_to_optional_int(raw.get("perf_max")),
                category=str(raw.get("category") or "ETC").upper().strip(),
                discount_rate=_to_decimal(raw.get("discount_rate")),
                category_cap=_to_optional_int(raw.get("category_cap")),
            )
            rule.validate()
        except (RuleValidationError, ValueError, TypeError) as exc:
            # 잘못된 규칙 하나 때문에 조항 전체를 버리지 않는다.
            logger.warning("혜택 규칙 파싱 실패, 건너뜁니다: %s", exc)
            return None
        return rule

    def _parse_exclusion(self, raw: Any) -> ExclusionRule | None:
        if not isinstance(raw, dict):
            return None
        try:
            rule = ExclusionRule(
                exclusion_type=ExclusionType(
                    str(raw.get("exclusion_type") or "").upper().strip()
                ),
                target_kind=TargetKind(
                    str(raw.get("target_kind") or "").upper().strip()
                ),
                target_value=str(raw.get("target_value") or "").upper().strip(),
            )
            rule.validate()
        except (RuleValidationError, ValueError, TypeError) as exc:
            logger.warning("제외 규칙 파싱 실패, 건너뜁니다: %s", exc)
            return None
        return rule


def _to_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        raise ValueError("정수 자리에 불리언이 왔습니다")
    return int(value)


def _to_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return _to_int(value)


def _to_decimal(value: Any) -> Decimal:
    if value is None:
        raise ValueError("할인율이 없습니다")
    try:
        # float 를 문자열로 거쳐 Decimal 로 만든다.
        # Decimal(0.05) 는 0.05000000000000000277... 이 된다.
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"할인율을 해석할 수 없습니다: {value}") from exc


__all__ = ["RuleExtractor", "SYSTEM_PROMPT", "USER_TEMPLATE", "LlmError"]
