"""라우팅 설명 생성 단위 테스트 — 네트워크 없이 실행된다.

test_rag.py의 _StubClient와 같은 패턴이다: LlmClient를 흉내 내는 스텁을
주입해 실제 LLM 호출 없이 성공·실패 경로를 검증한다.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from src.api.explain import generate_explanation
from src.common.exceptions import LlmBudgetExceededError, LlmPermanentError
from src.engine.route import RouteCandidate
from src.repository.card import BenefitRule
from src.repository.clause import ClauseRef


class _StubClient:
    """complete()만 흉내 낸다. generate_explanation은 이 메서드만 쓴다."""

    def __init__(self, text: str | None = None, error: Exception | None = None) -> None:
        self._text = text
        self._error = error
        self.last_prompt: str | None = None

    def complete(self, system: str, user: str, max_tokens: int = 2048) -> str:
        self.last_prompt = user
        if self._error is not None:
            raise self._error
        assert self._text is not None
        return self._text


def _candidate(**overrides) -> RouteCandidate:
    base = dict(
        card_id=1,
        card_name="테스트카드",
        pay_date=date(2026, 8, 25),
        payment_type="LUMP",
        installment_months=0,
        expected_discount=10_000,
        perf_achieved=True,
        perf_current=500_000,
        perf_required=300_000,
        rule_id=1,
    )
    base.update(overrides)
    return RouteCandidate(**base)


class TestGenerateExplanation:
    def test_정상_응답을_그대로_반환한다(self):
        client = _StubClient(text="이 카드는 실적을 채워 10,000원 할인이 적용됩니다.")

        result = generate_explanation(
            client, _candidate(), rule=None, clause=None, category="ONLINE", amount=100_000
        )

        assert result == "이 카드는 실적을 채워 10,000원 할인이 적용됩니다."

    def test_LLM_예산초과면_None을_반환한다(self):
        client = _StubClient(error=LlmBudgetExceededError("예산 초과"))

        result = generate_explanation(
            client, _candidate(), rule=None, clause=None, category="ONLINE", amount=100_000
        )

        assert result is None

    def test_LLM_인증실패면_None을_반환한다(self):
        client = _StubClient(error=LlmPermanentError("401"))

        result = generate_explanation(
            client, _candidate(), rule=None, clause=None, category="ONLINE", amount=100_000
        )

        assert result is None

    def test_빈_응답은_None으로_취급한다(self):
        client = _StubClient(text="   ")

        result = generate_explanation(
            client, _candidate(), rule=None, clause=None, category="ONLINE", amount=100_000
        )

        assert result is None

    def test_프롬프트에_계산된_숫자와_조항_원문이_들어간다(self):
        client = _StubClient(text="설명")
        rule = BenefitRule(1, 1, 300_000, None, "ONLINE", Decimal("0.1000"), 20_000, 9, True)
        clause = ClauseRef(content="온라인쇼핑 10% 할인", doc_name="테스트 안내장", page_no=3)

        generate_explanation(
            client, _candidate(), rule=rule, clause=clause, category="ONLINE", amount=100_000
        )

        assert client.last_prompt is not None
        assert "10,000원" in client.last_prompt  # expected_discount
        assert "적용 할인율: 10%" in client.last_prompt  # 10.0000%가 아니라 10%
        assert "온라인쇼핑 10% 할인" in client.last_prompt  # 조항 원문 그대로
