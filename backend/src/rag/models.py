"""약관 파이프라인 DTO.

LLM이 반환한 규칙은 DB에 넣기 전에 반드시 검증한다.
검증을 통과해도 verified=false 로 적재하고, 사람이 확인한 뒤에야 true 가 된다.
LLM 출력을 그대로 신뢰하지 않는 두 겹의 방어다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from src.common.exceptions import RuleValidationError

# spend_category 마스터에 존재하는 코드. schema.sql 과 반드시 일치해야 한다.
# LLM이 'FOOD' 같은 임의 코드를 만들어내면 FK 제약에 걸려 적재가 실패한다.
VALID_CATEGORIES: frozenset[str] = frozenset(
    {
        "ALL",
        "DINING",
        "CAFE",
        "DELIVERY",
        "GROCERY",
        "ONLINE",
        "TRANSPORT",
        "FUEL",
        "MEDICAL",
        "EDUCATION",
        "CULTURE",
        "TELECOM",
        "UTILITY",
        "TAX",
        "INSURANCE",
        "GIFT_CARD",
        "SUBSCRIPTION",
        "ETC",
    }
)

VALID_PAYMENT_TYPES: frozenset[str] = frozenset(
    {"LUMP", "INSTALLMENT", "INTEREST_FREE"}
)


class ExclusionType(StrEnum):
    PERFORMANCE = "PERFORMANCE"
    DISCOUNT = "DISCOUNT"
    BOTH = "BOTH"


class TargetKind(StrEnum):
    CATEGORY = "CATEGORY"
    MERCHANT = "MERCHANT"
    PAYMENT_TYPE = "PAYMENT_TYPE"


@dataclass(frozen=True, slots=True)
class Clause:
    """약관에서 잘라낸 조항 하나."""

    doc_name: str
    page_no: int
    content: str

    def __post_init__(self) -> None:
        if not self.content.strip():
            raise ValueError("조항 내용이 비어 있습니다")


@dataclass(frozen=True, slots=True)
class BenefitRule:
    """실적 구간별 혜택 규칙.

    card_benefit_rule 테이블과 1:1 대응한다.
    """

    perf_min: int
    perf_max: int | None
    category: str
    discount_rate: Decimal
    category_cap: int | None = None

    def validate(self) -> None:
        """DB 제약과 동일한 검증을 적재 전에 수행한다.

        DB에 맡기면 배치가 중간에 멈추고 어느 조항이 문제인지 찾기 어렵다.
        여기서 걸러내면 문제 조항을 로그로 특정할 수 있다.
        """
        if self.perf_min < 0:
            raise RuleValidationError("실적 하한이 음수입니다")
        if self.perf_max is not None and self.perf_max <= self.perf_min:
            raise RuleValidationError(
                f"실적 상한({self.perf_max})이 하한({self.perf_min}) 이하입니다"
            )
        if self.category not in VALID_CATEGORIES:
            raise RuleValidationError(
                f"spend_category 에 없는 카테고리입니다: {self.category}"
            )
        if not (Decimal(0) <= self.discount_rate <= Decimal(1)):
            raise RuleValidationError(
                f"할인율이 0~1 범위를 벗어났습니다: {self.discount_rate}"
            )
        if self.category_cap is not None and self.category_cap < 0:
            raise RuleValidationError("카테고리 한도가 음수입니다")

    @property
    def scope_key(self) -> tuple[int, int | None, str]:
        """uq_rule_scope UNIQUE 제약과 동일한 키.

        같은 카드 안에서 이 키가 겹치면 적재가 실패한다.
        """
        return (self.perf_min, self.perf_max, self.category)


@dataclass(frozen=True, slots=True)
class ExclusionRule:
    """실적 제외 또는 할인 제외 항목.

    두 개념이 다르다는 점이 중요하다. 무이자 할부는 실적에 안 잡히지만
    할인은 되는 카드가 있고, 그 반대도 있다.
    """

    exclusion_type: ExclusionType
    target_kind: TargetKind
    target_value: str

    def validate(self) -> None:
        if self.target_kind is TargetKind.CATEGORY:
            if self.target_value not in VALID_CATEGORIES:
                raise RuleValidationError(
                    f"spend_category 에 없는 카테고리입니다: {self.target_value}"
                )
        elif self.target_kind is TargetKind.PAYMENT_TYPE:
            if self.target_value not in VALID_PAYMENT_TYPES:
                raise RuleValidationError(
                    f"허용되지 않는 결제 방식입니다: {self.target_value}"
                )
        if not self.target_value.strip():
            raise RuleValidationError("제외 대상이 비어 있습니다")


@dataclass(slots=True)
class ExtractionResult:
    """조항 하나에서 뽑아낸 규칙 묶음.

    1단계 파이프라인의 산출물이다. 조항과 규칙이 한 객체에 함께 있으므로
    적재 시 clause_id 를 그대로 연결할 수 있고 별도 매칭이 필요 없다.
    """

    clause: Clause
    benefit_rules: list[BenefitRule] = field(default_factory=list)
    exclusion_rules: list[ExclusionRule] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """규칙이 없는 조항. 적재할 필요가 없다."""
        return not self.benefit_rules and not self.exclusion_rules

    def validate_all(self) -> None:
        for rule in self.benefit_rules:
            rule.validate()
        for rule in self.exclusion_rules:
            rule.validate()
