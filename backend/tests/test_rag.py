"""약관 파이프라인 테스트.

LLM 응답은 신뢰할 수 없다는 전제로, 잘못된 응답이 DB까지 도달하지 않는지
검증하는 데 초점을 맞춘다.
"""

from decimal import Decimal

import pytest

from src.common.exceptions import LlmPermanentError, RuleValidationError
from src.common.llm import parse_json_response
from src.rag.models import (
    BenefitRule,
    Clause,
    ExclusionRule,
    ExclusionType,
    ExtractionResult,
    TargetKind,
)
from src.rag.pdf_parser import filter_rule_candidates, split_into_clauses
from src.rag.rule_extractor import RuleExtractor


# ─────────────────────────────────────────────
# 규칙 검증
# ─────────────────────────────────────────────
class TestBenefitRuleValidation:
    def test_정상_규칙은_통과한다(self):
        rule = BenefitRule(
            perf_min=300_000,
            perf_max=500_000,
            category="DINING",
            discount_rate=Decimal("0.05"),
            category_cap=10_000,
        )
        rule.validate()  # 예외 없음

    def test_상한이_하한보다_작으면_거부한다(self):
        rule = BenefitRule(
            perf_min=500_000,
            perf_max=300_000,
            category="DINING",
            discount_rate=Decimal("0.05"),
        )
        with pytest.raises(RuleValidationError, match="실적 상한"):
            rule.validate()

    def test_마스터에_없는_카테고리는_거부한다(self):
        """LLM이 만들어낸 임의 코드가 FK 제약에 걸리기 전에 잡아낸다."""
        rule = BenefitRule(
            perf_min=300_000,
            perf_max=None,
            category="FOOD",  # spend_category 에 없음
            discount_rate=Decimal("0.05"),
        )
        with pytest.raises(RuleValidationError, match="spend_category"):
            rule.validate()

    @pytest.mark.parametrize("rate", ["1.5", "-0.1", "5"])
    def test_할인율이_범위를_벗어나면_거부한다(self, rate):
        """5%를 0.05가 아니라 5로 쓴 경우를 잡아낸다."""
        rule = BenefitRule(
            perf_min=0,
            perf_max=None,
            category="ALL",
            discount_rate=Decimal(rate),
        )
        with pytest.raises(RuleValidationError, match="할인율"):
            rule.validate()

    def test_scope_key는_UNIQUE_제약과_일치한다(self):
        rule = BenefitRule(
            perf_min=300_000,
            perf_max=500_000,
            category="ONLINE",
            discount_rate=Decimal("0.03"),
        )
        assert rule.scope_key == (300_000, 500_000, "ONLINE")


class TestExclusionRuleValidation:
    def test_실적_제외와_할인_제외를_구분한다(self):
        perf = ExclusionRule(
            ExclusionType.PERFORMANCE, TargetKind.CATEGORY, "TAX"
        )
        disc = ExclusionRule(
            ExclusionType.DISCOUNT, TargetKind.CATEGORY, "TRANSPORT"
        )
        perf.validate()
        disc.validate()
        assert perf.exclusion_type is not disc.exclusion_type

    def test_잘못된_결제방식은_거부한다(self):
        rule = ExclusionRule(
            ExclusionType.BOTH, TargetKind.PAYMENT_TYPE, "CASH"
        )
        with pytest.raises(RuleValidationError, match="결제 방식"):
            rule.validate()

    def test_카테고리_대상은_마스터를_따른다(self):
        rule = ExclusionRule(
            ExclusionType.PERFORMANCE, TargetKind.CATEGORY, "GIFTCARD"
        )
        with pytest.raises(RuleValidationError):
            rule.validate()


# ─────────────────────────────────────────────
# LLM 응답 파싱
# ─────────────────────────────────────────────
class TestParseJsonResponse:
    def test_순수_JSON을_파싱한다(self):
        assert parse_json_response('{"a": 1}') == {"a": 1}

    def test_코드_펜스를_제거한다(self):
        raw = '```json\n{"a": 1}\n```'
        assert parse_json_response(raw) == {"a": 1}

    def test_앞뒤_설명이_붙어도_추출한다(self):
        raw = '다음과 같습니다:\n{"a": 1}\n도움이 되었길 바랍니다.'
        assert parse_json_response(raw) == {"a": 1}

    def test_JSON이_없으면_영구_실패로_처리한다(self):
        """재시도해도 소용없으므로 LlmPermanentError 여야 한다."""
        with pytest.raises(LlmPermanentError):
            parse_json_response("죄송하지만 답변할 수 없습니다")

    def test_한_줄짜리_코드펜스도_처리한다(self):
        """실제 사고 재현: 개행 없이 ```json {...}``` 로 오면
        splitlines()[1:] 방식은 그 한 줄 전체를 잘라내 빈 문자열이 되고,
        결과적으로 유효한 JSON인데도 파싱 실패로 처리됐다.
        """
        raw = '```json {"a": 1}```'
        assert parse_json_response(raw) == {"a": 1}


# ─────────────────────────────────────────────
# 추출기
# ─────────────────────────────────────────────
class _StubClient:
    """LLM 호출 없이 고정 응답을 반환한다."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def complete_json(self, system: str, user: str, max_tokens: int = 2048) -> dict:
        return self._payload


@pytest.fixture
def clause() -> Clause:
    return Clause(
        doc_name="test.pdf",
        page_no=3,
        content="전월 실적 30만원 이상 시 온라인 결제 10% 할인, 무이자 할부 제외",
    )


class TestRuleExtractor:
    def test_정상_응답을_규칙으로_변환한다(self, clause):
        extractor = RuleExtractor(
            _StubClient(
                {
                    "benefit_rules": [
                        {
                            "perf_min": 300000,
                            "perf_max": None,
                            "category": "ONLINE",
                            "discount_rate": 0.1,
                            "category_cap": 20000,
                        }
                    ],
                    "exclusion_rules": [
                        {
                            "exclusion_type": "BOTH",
                            "target_kind": "PAYMENT_TYPE",
                            "target_value": "INTEREST_FREE",
                        }
                    ],
                }
            )
        )
        result = extractor.extract(clause, "테스트카드", "테스트")

        assert len(result.benefit_rules) == 1
        assert result.benefit_rules[0].category == "ONLINE"
        assert result.benefit_rules[0].discount_rate == Decimal("0.1")
        assert len(result.exclusion_rules) == 1
        assert not result.is_empty

    def test_잘못된_규칙만_건너뛰고_나머지는_살린다(self, clause):
        """한 규칙이 잘못됐다고 조항 전체를 버리면 안 된다."""
        extractor = RuleExtractor(
            _StubClient(
                {
                    "benefit_rules": [
                        {
                            "perf_min": 300000,
                            "category": "INVALID_CODE",
                            "discount_rate": 0.1,
                        },
                        {
                            "perf_min": 300000,
                            "category": "CAFE",
                            "discount_rate": 0.05,
                        },
                    ],
                    "exclusion_rules": [],
                }
            )
        )
        result = extractor.extract(clause, "테스트카드", "테스트")

        assert len(result.benefit_rules) == 1
        assert result.benefit_rules[0].category == "CAFE"

    def test_규칙이_없으면_빈_결과를_반환한다(self, clause):
        extractor = RuleExtractor(
            _StubClient({"benefit_rules": [], "exclusion_rules": []})
        )
        result = extractor.extract(clause, "테스트카드", "테스트")
        assert result.is_empty

    def test_할인율_부동소수_오차가_없다(self, clause):
        """Decimal(0.05) 는 0.05000000000000000277 이 된다.

        문자열을 거쳐야 정확한 값이 나온다.
        """
        extractor = RuleExtractor(
            _StubClient(
                {
                    "benefit_rules": [
                        {
                            "perf_min": 0,
                            "category": "ALL",
                            "discount_rate": 0.05,
                        }
                    ],
                    "exclusion_rules": [],
                }
            )
        )
        result = extractor.extract(clause, "테스트카드", "테스트")
        assert result.benefit_rules[0].discount_rate == Decimal("0.05")


# ─────────────────────────────────────────────
# 조항 분할
# ─────────────────────────────────────────────
class TestClauseSplitting:
    def test_번호_항목을_기준으로_자른다(self):
        text = (
            "1. 전월 실적 30만원 이상 시 온라인 결제 5% 할인이 적용됩니다.\n"
            "2. 무이자 할부 이용금액은 전월 실적 산정에서 제외됩니다.\n"
            "3. 세금 및 공과금 납부액은 실적에 포함되지 않습니다.\n"
        )
        assert len(split_into_clauses(text)) >= 2

    def test_너무_짧은_조각은_버리지_않고_직전_조각에_합친다(self):
        """짧다고 버리면 텍스트가 조용히 사라진다. 인접 조각에 흡수시킨다."""
        result = split_into_clauses("1. 짧음\n2. 또짧음\n")
        assert result == ["1. 짧음 2. 또짧음"]

    def test_제N조_안의_호_번호는_새_조항으로_분할하지_않는다(self):
        """실제 사고 재현: 제6조 안의 호(5, 6번)가 줄바꿈 뒤에 오면
        예전 정규식은 이를 새 조항 시작으로 오인해 조를 둘로 쪼갰고,
        뒤 조각이 MIN_CLAUSE_LENGTH 미달로 사라졌다(카드 C 제6조 사고).
        '제N조' 마커가 있으면 호 번호는 분할 경계가 아니어야 한다.
        """
        text = (
            "제6조(전월 이용실적 제외 대상) 다음 각 호의 이용금액은 전월 "
            "이용실적 산정에서 제외됩니다. 1\n. 국세 및 지방세. 2. 전기·가스·"
            "수도 등 공과금. 3. 상품권 및 기프트카드 구매금액. 4. 보험료. \n"
            "5. 학원비 등 교육비. 6. 무이자 할부 결제금액.\n"
        )
        result = split_into_clauses(text)
        assert len(result) == 1
        assert "학원비" in result[0]
        assert "무이자" in result[0]

    def test_제N조가_여러_개면_각각을_경계로_분할한다(self):
        text = (
            "제1조(목적) 이 약관은 카드 이용에 관한 사항을 정합니다.\n"
            "제2조(정의) 1. 회원이란 카드를 발급받은 자를 말합니다. "
            "2. 가맹점이란 카드로 결제할 수 있는 사업자를 말합니다.\n"
        )
        result = split_into_clauses(text)
        assert len(result) == 2
        assert result[0].startswith("제1조")
        assert result[1].startswith("제2조")
        # 제2조 안의 호 번호(1, 2)가 별도 조각으로 떨어지지 않아야 한다.
        assert "가맹점" in result[1]

    def test_키워드가_없는_조항은_후보에서_제외한다(self):
        """LLM 호출 비용을 줄이는 필터가 실제로 동작하는지 확인한다."""
        clauses = [
            Clause("a.pdf", 1, "전월 실적 30만원 이상 시 5% 할인이 적용됩니다."),
            Clause("a.pdf", 2, "카드 분실 시 즉시 고객센터로 연락하시기 바랍니다."),
        ]
        filtered = filter_rule_candidates(clauses)
        assert len(filtered) == 1
        assert "실적" in filtered[0].content


# ─────────────────────────────────────────────
# 추출 결과
# ─────────────────────────────────────────────
class TestExtractionResult:
    def test_validate_all은_모든_규칙을_검사한다(self):
        result = ExtractionResult(clause=Clause("a.pdf", 1, "테스트 조항 내용입니다"))
        result.benefit_rules.append(
            BenefitRule(0, None, "NOPE", Decimal("0.05"))
        )
        with pytest.raises(RuleValidationError):
            result.validate_all()
