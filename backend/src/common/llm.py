"""LLM 클라이언트.

두 가지를 분리해서 다룬다.

1. **제공자 추상화** — Gemini 로 확정했다(docs/decisions/002). 요청·응답 형식만
   어댑터로 감싸두면 LLM_PROVIDER 환경변수 하나로 교체할 수 있어, 무료 티어
   한도나 모델 정책이 바뀌어도 호출부를 고치지 않는다.

2. **배치와 런타임 프로파일** — 재시도 정책이 다르다.

   | 경로   | 기준            | 실패 시                       |
   |--------|-----------------|-------------------------------|
   | 배치   | 최대 시도 횟수  | 예외를 던져 호출부가 기록·재개 |
   | 런타임 | 총 소요 시간    | LlmBudgetExceededError        |

   런타임에서 stop_after_attempt 만 쓰면 응답 시간이 보장되지 않는다.
   시도 2회여도 각 호출이 10초씩 걸리면 20초가 된다. stop_after_delay 로
   총 예산을 걸어야 API 응답 시간을 통제할 수 있다.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from google.genai import types
from tenacity import (
    RetryError,
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    stop_after_delay,
    wait_exponential,
)

from src.common.config import Settings, get_settings
from src.common.exceptions import (
    LlmBudgetExceededError,
    LlmPermanentError,
    LlmTransientError,
)
from src.common.logging import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────
# 제공자 어댑터
# ─────────────────────────────────────────────
class LlmProvider(Protocol):
    """제공자별 요청·응답 형식 차이를 흡수한다."""

    def build_request(
        self, system: str, user: str, max_tokens: int
    ) -> tuple[str, dict[str, str], dict[str, Any]]:
        """(url, headers, json_body) 를 반환한다."""
        ...

    def extract_text(self, payload: dict[str, Any]) -> str:
        """응답 본문에서 생성된 텍스트만 뽑아낸다."""
        ...


class AnthropicProvider:
    """Anthropic Messages API."""

    BASE_URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model

    def build_request(
        self, system: str, user: str, max_tokens: int
    ) -> tuple[str, dict[str, str], dict[str, Any]]:
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        body: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        return self.BASE_URL, headers, body

    def extract_text(self, payload: dict[str, Any]) -> str:
        # content 는 블록 배열이다. 위치를 가정하지 말고 type 으로 걸러낸다.
        blocks = payload.get("content", [])
        return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")


class OpenAiProvider:
    """OpenAI Chat Completions API."""

    BASE_URL = "https://api.openai.com/v1/chat/completions"

    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model

    def build_request(
        self, system: str, user: str, max_tokens: int
    ) -> tuple[str, dict[str, str], dict[str, Any]]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        body: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        return self.BASE_URL, headers, body

    def extract_text(self, payload: dict[str, Any]) -> str:
        choices = payload.get("choices", [])
        if not choices:
            return ""
        return choices[0].get("message", {}).get("content", "") or ""


class GeminiProvider:
    """Gemini generateContent REST API.

    google-genai SDK는 네트워크 호출을 스스로 수행하는 방식이라, LlmClient가
    httpx로 직접 쏘는 현재 구조(build_request가 반환한 url/headers/body를
    그대로 전송)와 맞지 않는다(docs/decisions/002는 SDK를 "REST 직접 호출보다
    이점이 크다"는 이유로 선택했지만, 그 이점은 응답 스키마 지원이지 전송
    경로 자체는 아니다).

    그래서 SDK는 responseSchema 구성에만 쓴다. google.genai.types.Schema는
    REST JSON과 1:1 대응하도록 만들어져 있어 model_dump(by_alias=True)로
    바로 REST 바디에 넣을 수 있다. 나머지(contents, systemInstruction 등)는
    Gemini REST API 문서에 정의된 그대로 직접 구성한다 — SDK가 편의상
    받아주는 문자열 축약형(system_instruction="...")은 실제 전송 시
    SDK 내부에서 Content 객체로 정규화되므로, model_dump만으로는 그 변환을
    재현할 수 없다. 이렇게 하면 재시도·타임아웃·예산 로직(LlmClient)을
    Gemini 전용으로 따로 만들 필요가 없다.
    """

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(
        self,
        api_key: str,
        model: str,
        response_schema: types.Schema | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._response_schema = response_schema

    def build_request(
        self, system: str, user: str, max_tokens: int
    ) -> tuple[str, dict[str, str], dict[str, Any]]:
        url = f"{self.BASE_URL}/{self._model}:generateContent"
        headers = {
            "x-goog-api-key": self._api_key,
            "content-type": "application/json",
        }

        generation_config: dict[str, Any] = {"maxOutputTokens": max_tokens}
        if self._response_schema is not None:
            # responseMimeType 없이 responseSchema만 주면 무시된다.
            # 자유 텍스트로 답하고 파싱 방어에 기대는 대신, 둘을 함께
            # 지정해 출력 형식 자체를 강제한다.
            generation_config["responseMimeType"] = "application/json"
            generation_config["responseSchema"] = self._response_schema.model_dump(
                exclude_none=True, by_alias=True
            )

        body: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": generation_config,
        }
        return url, headers, body

    def extract_text(self, payload: dict[str, Any]) -> str:
        # candidates가 비면(안전 필터링 등) 후속 파싱이 아니라 여기서
        # 빈 문자열로 끝낸다. 호출부가 JSON 파싱 실패로 한 번 더 헤매지 않도록.
        candidates = payload.get("candidates", [])
        if not candidates:
            return ""
        parts = candidates[0].get("content", {}).get("parts", [])
        return "".join(p.get("text", "") for p in parts if "text" in p)


def build_provider(
    settings: Settings, *, response_schema: types.Schema | None = None
) -> LlmProvider:
    """response_schema는 Gemini에만 의미가 있다.

    다른 제공자로 전환해도 호출부(예: RuleExtractor 조립 코드)가 분기할
    필요가 없도록, Gemini가 아니면 조용히 무시한다.
    """
    if settings.llm_provider == "anthropic":
        return AnthropicProvider(settings.llm_api_key, settings.llm_model)
    if settings.llm_provider == "gemini":
        return GeminiProvider(
            settings.llm_api_key, settings.llm_model, response_schema=response_schema
        )
    return OpenAiProvider(settings.llm_api_key, settings.llm_model)


# ─────────────────────────────────────────────
# 호출 프로파일
# ─────────────────────────────────────────────
@dataclass(frozen=True)
class RetryProfile:
    """재시도 정책.

    두 기준을 동시에 쓰지 않는다. 배치는 시도 횟수(max_retry), 런타임은 총
    소요 시간(budget_ms)으로 중단한다. 런타임에 횟수를 함께 두면 실제로는
    쓰이지 않는데 설정값만 존재해, 그 값을 바꾸면 동작이 달라진다고 오해하게
    된다. 쓰지 않는 쪽은 None 으로 비워 어느 기준이 적용되는지 드러낸다.
    """

    name: str
    timeout_ms: int
    max_retry: int | None = None
    budget_ms: int | None = None


def batch_profile(settings: Settings | None = None) -> RetryProfile:
    s = settings or get_settings()
    return RetryProfile(
        name="batch",
        timeout_ms=s.llm_batch_timeout_ms,
        max_retry=s.llm_batch_max_retry,
        budget_ms=None,
    )


def runtime_profile(settings: Settings | None = None) -> RetryProfile:
    s = settings or get_settings()
    return RetryProfile(
        name="runtime",
        # 개별 호출 타임아웃이 총 예산보다 크면 예산이 의미를 잃는다.
        timeout_ms=min(s.llm_runtime_timeout_budget_ms, 3_000),
        max_retry=None,
        budget_ms=s.llm_runtime_timeout_budget_ms,
    )


# ─────────────────────────────────────────────
# 클라이언트
# ─────────────────────────────────────────────
class LlmClient:
    """제공자와 재시도 정책을 조합한 호출자."""

    def __init__(
        self,
        profile: RetryProfile,
        provider: LlmProvider | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._provider = provider or build_provider(self._settings)
        self._profile = profile

    # ---------- public ----------
    def complete(self, system: str, user: str, max_tokens: int = 2048) -> str:
        """텍스트를 생성한다. 실패 시 예외를 던진다."""
        # stop_after_delay 는 "새 시도를 시작할지"만 본다. 마지막 시도가 예산
        # 경계에서 시작하면 그 시도의 타임아웃만큼 총 시간이 더 늘어난다.
        # 실제로 예산 3.5초인데 응답이 8.8초 걸린 적이 있다(제공자가 429 대신
        # 응답을 아예 주지 않고 매달린 경우). 각 시도의 타임아웃을 남은 예산
        # 안으로 줄여, 예산이 총 소요 시간을 실제로 묶게 한다.
        deadline = (
            time.monotonic() + self._profile.budget_ms / 1000
            if self._profile.budget_ms is not None
            else None
        )

        if self._profile.budget_ms is not None:
            stop = stop_after_delay(self._profile.budget_ms / 1000)
        elif self._profile.max_retry is not None:
            stop = stop_after_attempt(self._profile.max_retry)
        else:
            raise ValueError(
                f"재시도 중단 기준이 없습니다: profile={self._profile.name}"
            )

        retrying = Retrying(
            stop=stop,
            wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
            retry=retry_if_exception_type(LlmTransientError),
            reraise=False,
        )
        try:
            for attempt in retrying:
                with attempt:
                    return self._call_once(system, user, max_tokens, deadline)
        except RetryError as exc:
            if self._profile.budget_ms is not None:
                raise LlmBudgetExceededError(
                    f"런타임 예산 {self._profile.budget_ms}ms 초과"
                ) from exc
            raise LlmTransientError(
                f"재시도 {self._profile.max_retry}회 모두 실패"
            ) from exc
        raise LlmTransientError("호출이 수행되지 않았습니다")  # 도달하지 않음

    def complete_json(
        self, system: str, user: str, max_tokens: int = 2048
    ) -> dict[str, Any]:
        """JSON 응답을 파싱해 반환한다.

        모델이 코드 펜스를 붙이는 경우가 흔해 제거 후 파싱한다.
        """
        raw = self.complete(system, user, max_tokens)
        return parse_json_response(raw)

    # ---------- internal ----------
    def _call_once(
        self,
        system: str,
        user: str,
        max_tokens: int,
        deadline: float | None = None,
    ) -> str:
        """한 번 호출한다.

        이 메서드에서 나가는 예외는 **반드시 LlmError 계열이어야 한다.**
        호출부(설명 생성 등)는 `except LlmError` 로 대체 응답 경로를 잡는데,
        다른 계열이 새어 나가면 그 방어를 통과해 계산 결과까지 함께 사라진다.
        실제로 API 키에 비ASCII 문자가 섞였을 때 httpx 가 헤더를 만들다
        UnicodeEncodeError(ValueError 하위)를 던져 /api/route 가 500 이 됐다.
        """
        try:
            url, headers, body = self._provider.build_request(system, user, max_tokens)
        except Exception as exc:
            # 요청 구성 실패는 설정이 잘못된 것이라 재시도해도 같은 결과다.
            raise LlmPermanentError(
                f"LLM 요청을 구성하지 못했습니다: {type(exc).__name__}"
            ) from exc

        timeout = self._profile.timeout_ms / 1000
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise LlmBudgetExceededError(
                    f"런타임 예산 {self._profile.budget_ms}ms 초과"
                )
            timeout = min(timeout, remaining)

        try:
            response = httpx.post(url, headers=headers, json=body, timeout=timeout)
        except httpx.TimeoutException as exc:
            raise LlmTransientError(f"LLM 호출 타임아웃 ({timeout}s)") from exc
        except httpx.HTTPError as exc:
            raise LlmTransientError(f"LLM 호출 네트워크 오류: {exc}") from exc
        except Exception as exc:
            # httpx 는 요청을 전송하기 전 헤더·본문을 인코딩하는데, 여기서 나는
            # 실패는 httpx.HTTPError 가 아니라 표준 예외로 올라온다.
            # 예외 문구에 원인 값이 그대로 실릴 수 있어(UnicodeEncodeError 는
            # 문제된 문자를 메시지에 담는다) 타입 이름만 남긴다 — API 키가
            # 로그와 응답에 새는 경로를 만들지 않는다.
            raise LlmPermanentError(
                f"LLM 호출을 보내지 못했습니다: {type(exc).__name__}"
            ) from exc

        self._raise_for_status(response)

        try:
            payload = response.json()
        except ValueError as exc:
            raise LlmTransientError("LLM 응답이 JSON이 아닙니다") from exc

        try:
            return self._provider.extract_text(payload)
        except Exception as exc:
            # 제공자가 예상과 다른 형태의 응답을 주면 파싱이 깨질 수 있다.
            # 응답 형태가 바뀐 것이므로 재시도해도 같다.
            raise LlmPermanentError(
                f"LLM 응답에서 텍스트를 얻지 못했습니다: {type(exc).__name__}"
            ) from exc

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        """상태 코드를 일시적 실패와 영구 실패로 나눈다.

        재시도해도 소용없는 실패(401, 400)를 재시도하면 시간과 비용만 든다.
        """
        if response.status_code < 400:
            return

        if response.status_code == 429 or response.status_code >= 500:
            retry_after = response.headers.get("retry-after")
            wait_s: float | None = None
            if retry_after:
                try:
                    wait_s = float(retry_after)
                except ValueError:
                    wait_s = None
            logger.warning(
                "LLM 일시적 실패 status=%s retry_after=%s",
                response.status_code,
                retry_after,
            )
            raise LlmTransientError(
                f"LLM 일시적 실패: {response.status_code}", retry_after_s=wait_s
            )

        # 본문에 키가 실릴 수 있으므로 상태 코드만 남긴다.
        raise LlmPermanentError(f"LLM 요청 실패: {response.status_code}")


def parse_json_response(raw: str) -> dict[str, Any]:
    """모델 응답에서 JSON 객체를 뽑아낸다.

    프롬프트로 JSON만 반환하라고 지시해도 코드 펜스나 설명이 붙는 경우가 있다.
    """
    text = raw.strip()

    if text.startswith("```"):
        # ```json ... ``` 형태에서 내용만 남긴다.
        # 줄 단위(splitlines()[1:])로 벗기면 코드펜스와 내용이 개행 없이
        # 한 줄에 붙어 오는 경우(```json {...}```) 그 한 줄 전체가
        # 잘려나가 빈 문자열이 된다. 정규식으로 시작/끝 펜스만 벗겨내면
        # 한 줄이든 여러 줄이든 동일하게 처리된다.
        text = re.sub(r"^```[a-zA-Z0-9_+-]*\s*", "", text)
        text = re.sub(r"```\s*$", "", text)
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 앞뒤에 설명이 붙은 경우 첫 중괄호부터 마지막 중괄호까지 잘라 재시도한다.
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise LlmPermanentError("LLM 응답을 JSON으로 파싱할 수 없습니다") from exc

    raise LlmPermanentError("LLM 응답에 JSON 객체가 없습니다")
