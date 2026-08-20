"""RuleExtractor용 Gemini 응답 스키마.

category enum을 코드에 다시 적으면(rag/models.py의 VALID_CATEGORIES처럼)
spend_category 마스터가 바뀔 때 조용히 어긋난다. 여기서는 스키마를 만들 때
마스터를 직접 조회해 enum을 구성한다.

다만 조항마다 스키마를 새로 만들 필요는 없고 마스터도 배치 실행 중에는
바뀌지 않으므로, 조항 수만큼 DB를 왕복하지 않도록 프로세스 생애주기 동안
캐싱한다.
"""

from __future__ import annotations

from google.genai import types
from sqlalchemy import text
from sqlalchemy.orm import Session

_cached_categories: tuple[str, ...] | None = None


def get_category_codes(session: Session, *, refresh: bool = False) -> tuple[str, ...]:
    """spend_category.code 전체를 캐싱해 반환한다.

    refresh=True 를 넘기면 캐시를 무시하고 다시 조회한다. 배치 한 번 실행
    중에는 마스터가 바뀔 일이 없으므로 기본은 프로세스당 한 번만 조회한다.
    """
    global _cached_categories
    if _cached_categories is None or refresh:
        rows = session.execute(
            text("SELECT code FROM spend_category ORDER BY sort_no")
        ).all()
        _cached_categories = tuple(r[0] for r in rows)
    return _cached_categories


def build_extraction_response_schema(categories: tuple[str, ...]) -> types.Schema:
    """RuleExtractor가 기대하는 JSON 응답 구조를 Gemini 스키마로 못박는다.

    benefit_rules[].category만 enum으로 제한한다. exclusion_rules[].target_value는
    target_kind(CATEGORY/MERCHANT/PAYMENT_TYPE)에 따라 가리키는 값의 종류가
    달라지는 다형 필드라 enum 하나로 못박을 수 없다 — 이 값의 검증은 지금처럼
    ExclusionRule.validate()의 사후 검사에 맡긴다.
    """
    benefit_rule_schema = types.Schema(
        type=types.Type.OBJECT,
        properties={
            "perf_min": types.Schema(type=types.Type.INTEGER),
            "perf_max": types.Schema(type=types.Type.INTEGER, nullable=True),
            "category": types.Schema(type=types.Type.STRING, enum=list(categories)),
            "discount_rate": types.Schema(type=types.Type.NUMBER),
            "category_cap": types.Schema(type=types.Type.INTEGER, nullable=True),
        },
        required=["perf_min", "category", "discount_rate"],
    )
    exclusion_rule_schema = types.Schema(
        type=types.Type.OBJECT,
        properties={
            "exclusion_type": types.Schema(
                type=types.Type.STRING, enum=["PERFORMANCE", "DISCOUNT", "BOTH"]
            ),
            "target_kind": types.Schema(
                type=types.Type.STRING,
                enum=["CATEGORY", "MERCHANT", "PAYMENT_TYPE"],
            ),
            "target_value": types.Schema(type=types.Type.STRING),
        },
        required=["exclusion_type", "target_kind", "target_value"],
    )
    return types.Schema(
        type=types.Type.OBJECT,
        properties={
            "benefit_rules": types.Schema(
                type=types.Type.ARRAY, items=benefit_rule_schema
            ),
            "exclusion_rules": types.Schema(
                type=types.Type.ARRAY, items=exclusion_rule_schema
            ),
        },
        required=["benefit_rules", "exclusion_rules"],
    )
