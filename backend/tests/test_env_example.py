"""저장소 루트 .env.example 이 실제 결정 사항과 일치하는지 확인한다.

이 파일 자체는 로직이 아니라 설정 템플릿이지만, 팀 리뷰에서 LLM_PROVIDER
기본값이 docs/decisions/002(Gemini 확정)와 어긋나 있다는 지적이 있었다.
값이 조용히 되돌아가는 걸 막기 위해 회귀 테스트로 고정해둔다.
"""

from __future__ import annotations

from pathlib import Path

_ENV_EXAMPLE = Path(__file__).resolve().parent.parent.parent / ".env.example"


def test_LLM_PROVIDER_기본값이_gemini다():
    """docs/decisions/002에서 Gemini로 확정했다. 기본값이 다시 어긋나면
    이 테스트가 잡아낸다.
    """
    content = _ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "LLM_PROVIDER=gemini" in content
