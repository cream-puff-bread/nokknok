"""라우팅 결과 설명 생성 — 런타임 LLM 프로파일.

계산은 이미 끝난 상태다(src/engine/route.py). 여기서는 그 결과를 문장으로
풀어 쓸 뿐 숫자를 새로 만들거나 바꾸지 않는다 — 프롬프트에 이미 계산된
값만 넣고 "이 값을 설명해라"라고만 지시하는 이유다. LLM이 계산하지
않는다는 원칙(CLAUDE.md)은 배치 규칙 변환뿐 아니라 여기도 해당한다.

실패하면(예산 초과·네트워크 오류·인증 실패) None을 반환한다. 호출부는
그대로 explanation에 넣으면 된다 — LLM 실패 시에도 계산 결과 자체는
반드시 응답에 포함돼야 한다는 원칙 때문에, 여기서 예외를 밖으로
던지지 않는다.
"""

from __future__ import annotations

from src.common.exceptions import LlmError
from src.common.llm import LlmClient
from src.common.logging import get_logger
from src.engine.route import RouteCandidate
from src.repository.card import BenefitRule
from src.repository.clause import ClauseRef

logger = get_logger(__name__)

_SYSTEM_PROMPT = (
    "너는 카드 결제 추천 결과를 이용자에게 설명하는 보조 도우미다. "
    "아래에 주어진 숫자와 약관 조항만 근거로 2~3문장의 한국어 설명을 써라. "
    "새로운 금액이나 비율을 계산하거나 추정하지 마라 — 모든 숫자는 이미 "
    "계산되어 주어진다. 주어지지 않은 내용은 지어내지 마라."
)


def _build_prompt(
    candidate: RouteCandidate,
    rule: BenefitRule | None,
    clause: ClauseRef | None,
    category: str,
    amount: int,
) -> str:
    lines = [
        f"카드: {candidate.card_name}",
        f"결제 카테고리: {category}",
        f"결제 금액: {amount:,}원",
        f"예상 할인액: {candidate.expected_discount:,}원",
        f"실적(현재/필요): {candidate.perf_current:,}원 / {candidate.perf_required:,}원",
        f"실적 조건: {'충족' if candidate.perf_achieved else '미충족'}",
    ]
    if rule is not None:
        # discount_rate는 NUMERIC(5,4)라 그대로 곱하면 "10.0000%"처럼 나온다.
        # 프롬프트에 불필요한 0을 넣으면 모델이 자릿수를 그대로 따라 읽어
        # "10.0000퍼센트"라고 어색하게 설명할 수 있어 사람이 쓰는 표기로 다듬는다.
        rate_pct = f"{rule.discount_rate * 100:f}".rstrip("0").rstrip(".")
        lines.append(f"적용 할인율: {rate_pct}%")
        if rule.category_cap is not None:
            lines.append(f"카테고리 할인 한도: {rule.category_cap:,}원")
    if clause is not None:
        lines.append(f"근거 조항({clause.doc_name}): {clause.content}")
    return "\n".join(lines)


def generate_explanation(
    client: LlmClient,
    candidate: RouteCandidate,
    rule: BenefitRule | None,
    clause: ClauseRef | None,
    category: str,
    amount: int,
) -> str | None:
    prompt = _build_prompt(candidate, rule, clause, category, amount)
    try:
        text = client.complete(_SYSTEM_PROMPT, prompt, max_tokens=300)
    except LlmError as exc:
        logger.warning("설명 생성 실패, explanation=null로 대체: %s", exc)
        return None
    return text.strip() or None
