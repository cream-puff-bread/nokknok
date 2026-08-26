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


class QueryParseError(LlmError):
    """자연어 질의에서 계산에 필요한 값을 얻지 못했다.

    설명 생성 실패와 성격이 다르다. 설명은 없어도 계산 결과를 낼 수 있어
    explanation=null 로 넘어가지만, 질의 파싱이 실패하면 무엇을 계산할지
    자체를 모르므로 계산을 시작할 수 없다. 호출부는 422 로 응답한다.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"질의 해석 실패: {reason}")
        self.reason = reason


# ─────────────────────────────────────────────
# 최적화 엔진
# ─────────────────────────────────────────────
class NoVerifiedRuleError(NokknokError):
    """검수를 통과한 규칙을 가진 카드가 하나도 없다.

    verified=false 규칙은 판정에 쓰지 않는다. 일부 카드만 제외되는 것은
    정상이며 그때는 계산을 계속하고 제외 카드 수만 알린다. 후보가 전부
    사라져 best 를 만들 수 없을 때만 이 예외를 던진다.
    """

    def __init__(self, excluded_cards: int) -> None:
        super().__init__(
            f"검수를 통과한 규칙이 있는 카드가 없습니다 (제외 {excluded_cards}장)"
        )
        self.excluded_cards = excluded_cards


class InvalidCategoryError(NokknokError):
    """spend_category 마스터에 없는 카테고리 코드다.

    contracts/api-spec.yaml의 ErrorResponse.code 중 INVALID_CATEGORY와
    짝지어진다(src/api/errors.py). 카테고리 오탈자를 여기서 걸러내지
    않으면 select_rule이 조용히 매치 실패해 할인 0원으로 계산된다 —
    CLAUDE.md가 경계하는 "그럴듯하지만 틀린 숫자" 실패 유형이다.
    """

    def __init__(self, category: str) -> None:
        super().__init__(f"등록되지 않은 소비 카테고리입니다: {category}")
        self.category = category


class InvalidAmountError(NokknokError):
    """amount가 0 이하다. ErrorResponse.code의 INVALID_AMOUNT와 짝지어진다."""

    def __init__(self, amount: int) -> None:
        super().__init__(f"금액은 0보다 커야 합니다: {amount}")
        self.amount = amount


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
