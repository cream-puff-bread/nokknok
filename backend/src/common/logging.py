"""로깅 설정.

개인 금융정보는 로그에 남기지 않는다. 카드번호, 계좌번호처럼 형태가 뚜렷한
값은 필터에서 한 번 더 걸러내지만, 애초에 로그 인자로 넘기지 않는 것이 원칙이다.
"""

import logging
import re
import sys

from src.common.config import get_settings

# 카드번호(13~16자리)와 계좌번호로 보이는 긴 숫자열
_CARD_PATTERN = re.compile(r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{1,4}\b")
_ACCOUNT_PATTERN = re.compile(r"\b\d{10,14}\b")


class SensitiveDataFilter(logging.Filter):
    """실수로 로그에 들어간 민감 정보를 마스킹한다.

    이 필터는 최후의 방어선이다. 이것에 의존하지 말고 로그 인자 자체에
    민감 정보를 넣지 않는다.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self._mask(record.msg)
        if record.args:
            record.args = tuple(
                self._mask(a) if isinstance(a, str) else a for a in record.args
            )
        return True

    @staticmethod
    def _mask(text: str) -> str:
        text = _CARD_PATTERN.sub("[CARD]", text)
        text = _ACCOUNT_PATTERN.sub("[ACCOUNT]", text)
        return text


def _force_utf8(stream):
    """스트림 인코딩을 UTF-8로 강제한다.

    Windows 콘솔 기본 코드페이지(cp949)는 한글은 대부분 표현하지만
    em-dash(—) 같은 일부 문자는 표현 범위 밖이라 로그를 남기는 순간
    UnicodeEncodeError로 죽는다. 문제된 문자 하나만 바꿔서 넘어가면
    다음에 다른 문자에서 또 터진다 — 인코딩 자체를 UTF-8로 강제해야
    이 클래스의 오류가 재발하지 않는다. reconfigure가 없는 스트림
    (테스트에서 StringIO 등을 handler에 직접 넘기는 경우)은 그대로 둔다.
    """
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8", errors="backslashreplace")
    return stream


def setup_logging() -> None:
    """루트 로거를 초기화한다. 애플리케이션 진입점에서 한 번만 호출한다."""
    settings = get_settings()

    handler = logging.StreamHandler(_force_utf8(sys.stdout))
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-7s %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    handler.addFilter(SensitiveDataFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())

    # httpx 는 요청마다 INFO 로그를 남겨 시끄럽다. URL에 키가 실릴 수도 있다.
    logging.getLogger("httpx").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
