"""도메인 예외.

호출부가 상황을 구분해 처리할 수 있도록 계층을 나눈다.
특히 LLM 실패는 '재시도해도 소용없는 실패'와 '일시적 실패'를 구분해야
재시도 정책을 올바르게 적용할 수 있다.
"""


class NokknokError(Exception):
    """모든 도메인 예외의 최상위."""


# ─────────────────────────────────────────────
# 데이터 소스
# ─────────────────────────────────────────────
class DataSourceError(NokknokError):
    """거래 데이터 조회 실패."""


class PersonaNotFoundError(DataSourceError):
    def __init__(self, identifier: int | str) -> None:
        super().__init__(f"페르소나를 찾을 수 없습니다: {identifier}")
        self.identifier = identifier


class UnsupportedFileFormatError(DataSourceError):
    def __init__(self, suffix: str) -> None:
        super().__init__(f"지원하지 않는 파일 형식입니다: {suffix}")
        self.suffix = suffix


# ─────────────────────────────────────────────
# LLM
# ─────────────────────────────────────────────
class LlmError(NokknokError):
    """LLM 호출 관련 실패의 상위."""


class LlmTransientError(LlmError):
    """일시적 실패. 재시도할 가치가 있다.

    429(rate limit), 5xx, 네트워크 타임아웃이 여기에 해당한다.
    """

    def __init__(self, message: str, retry_after_s: float | None = None) -> None:
        super().__init__(message)
        # 응답에 Retry-After 헤더가 있으면 백오프 계산보다 우선한다.
        self.retry_after_s = retry_after_s


class LlmPermanentError(LlmError):
    """재시도해도 소용없는 실패.

    401(인증), 400(잘못된 요청)이 여기에 해당한다.
    재시도하면 시간과 비용만 낭비된다.
    """


class LlmBudgetExceededError(LlmError):
    """런타임 총 예산을 초과했다.

    호출부는 이 예외를 잡아 대체 응답(설명 없이 계산 결과만)을 반환한다.
    """


# ─────────────────────────────────────────────
# 약관 파이프라인
# ─────────────────────────────────────────────
class ClausePipelineError(NokknokError):
    """약관 파싱·규칙 변환 실패."""


class RuleValidationError(ClausePipelineError):
    """LLM이 반환한 규칙이 스키마 제약을 만족하지 않는다.

    검수 이전 단계에서 걸러내야 DB에 잘못된 규칙이 들어가지 않는다.
    """

    def __init__(self, reason: str, payload: dict | None = None) -> None:
        super().__init__(f"규칙 검증 실패: {reason}")
        self.reason = reason
        self.payload = payload
