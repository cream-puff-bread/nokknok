"""LlmClient 의 실패 계약 테스트.

이 클라이언트에서 나가는 예외는 **반드시 LlmError 계열이어야 한다.**
호출부는 `except LlmError` 로 대체 응답 경로를 잡는데, 다른 계열이 새어
나가면 그 방어를 통과해 계산 결과까지 함께 사라진다.

실제로 그런 일이 있었다. API 키에 비ASCII 문자가 섞였을 때 httpx 가 헤더를
만들다 UnicodeEncodeError(ValueError 하위)를 던져 /api/route 가 500 을 냈고,
정상 계산된 카드 판정·할인액·근거 조항이 응답에서 통째로 사라졌다.

네트워크를 타지 않는다. 요청을 만드는 단계에서 실패하거나 httpx.post 를
바꿔치기해 검증한다.
"""

from __future__ import annotations

import time

import httpx
import pytest

from src.common.config import Settings
from src.common.exceptions import (
    LlmBudgetExceededError,
    LlmError,
    LlmPermanentError,
    LlmTransientError,
)
from src.common.llm import GeminiProvider, LlmClient, RetryProfile

# 재시도를 기다리지 않도록 시도 1회짜리 배치 프로파일을 쓴다.
PROFILE = RetryProfile(name="test", timeout_ms=1000, max_retry=1)

SETTINGS = Settings(_env_file=None)  # type: ignore[call-arg]


def client(provider) -> LlmClient:
    return LlmClient(PROFILE, provider=provider, settings=SETTINGS)


class _BrokenBuildProvider:
    def build_request(self, system: str, user: str, max_tokens: int):
        raise RuntimeError("스키마 구성 실패")

    def extract_text(self, payload: dict) -> str:
        return ""


class _BrokenExtractProvider:
    def build_request(self, system: str, user: str, max_tokens: int):
        return "https://example.invalid/v1", {"content-type": "application/json"}, {}

    def extract_text(self, payload: dict) -> str:
        raise KeyError("candidates")


class Test실패는_전부_LlmError로_나온다:
    def test_비ASCII_API_키는_LlmPermanentError다(self):
        """자리표시자나 공백이 섞인 키가 들어오면 헤더 인코딩에서 터진다.

        이 경우 UnicodeEncodeError 가 그대로 새어 나가면 호출부의
        except LlmError 를 통과해 계산 결과까지 사라진다.
        """
        provider = GeminiProvider("제미나이키", "gemini-3.5-flash-lite")

        with pytest.raises(LlmPermanentError):
            client(provider).complete("system", "user")

    def test_요청_구성_실패도_LlmError다(self):
        with pytest.raises(LlmError):
            client(_BrokenBuildProvider()).complete("system", "user")

    def test_응답_파싱_실패도_LlmError다(self, monkeypatch):
        monkeypatch.setattr(
            httpx,
            "post",
            lambda *a, **k: httpx.Response(200, json={"unexpected": True}),
        )

        with pytest.raises(LlmError):
            client(_BrokenExtractProvider()).complete("system", "user")

    def test_네트워크_오류는_일시적_실패로_남는다(self, monkeypatch):
        """재시도할 가치가 있는 실패까지 영구 실패로 바꾸면 안 된다."""

        def _fail(*args, **kwargs):
            raise httpx.ConnectError("연결 실패")

        monkeypatch.setattr(httpx, "post", _fail)

        with pytest.raises(LlmTransientError):
            client(_BrokenExtractProvider()).complete("system", "user")


class Test예외에_키가_실리지_않는다:
    def test_비ASCII_키가_예외_문구에_없다(self):
        """UnicodeEncodeError 는 문제된 문자를 메시지에 담는다.

        그대로 옮기면 API 키 일부가 로그와 응답에 새어 나간다.
        """
        secret = "제미나이키값"
        provider = GeminiProvider(secret, "gemini-3.5-flash-lite")

        with pytest.raises(LlmError) as exc_info:
            client(provider).complete("system", "user")

        assert secret not in str(exc_info.value)
        for char in secret:
            assert char not in str(exc_info.value)


class Test예산이_총_소요_시간을_묶는다:
    """stop_after_delay 는 "새 시도를 시작할지"만 본다.

    마지막 시도가 예산 경계에서 시작하면 그 시도의 타임아웃만큼 총 시간이 더
    늘어난다. 실제로 예산 3.5초인데 응답이 8.8초 걸린 적이 있다 — 제공자가
    429 대신 응답을 아예 주지 않고 매달린 경우다. 무료 티어 할당량이 소진되면
    깔끔한 429 가 아니라 이런 형태로 나타난다.
    """

    def test_응답하지_않는_제공자에도_예산_안에_끝난다(self, monkeypatch):
        budget_ms = 600
        profile = RetryProfile(
            name="runtime-test", timeout_ms=5_000, budget_ms=budget_ms
        )

        def _hang(*args, **kwargs):
            # 호출부가 넘긴 타임아웃을 그대로 존중하는 제공자를 흉내낸다.
            time.sleep(kwargs.get("timeout", 5))
            raise httpx.ReadTimeout("응답 없음")

        monkeypatch.setattr(httpx, "post", _hang)
        client = LlmClient(profile, provider=_BrokenExtractProvider(), settings=SETTINGS)

        started = time.monotonic()
        with pytest.raises(LlmBudgetExceededError):
            client.complete("system", "user")
        elapsed_ms = (time.monotonic() - started) * 1000

        # 개별 타임아웃(5초)이 예산 안으로 줄어들지 않으면 여기서 5초를 넘긴다.
        assert elapsed_ms < budget_ms * 2, f"{elapsed_ms:.0f}ms 걸림"

    def test_예산이_이미_지났으면_호출하지_않는다(self, monkeypatch):
        called = False

        def _record(*args, **kwargs):
            nonlocal called
            called = True
            raise httpx.ReadTimeout("응답 없음")

        monkeypatch.setattr(httpx, "post", _record)
        profile = RetryProfile(name="runtime-test", timeout_ms=1_000, budget_ms=1)
        client = LlmClient(profile, provider=_BrokenExtractProvider(), settings=SETTINGS)

        time.sleep(0.01)
        with pytest.raises(LlmError):
            client.complete("system", "user")
