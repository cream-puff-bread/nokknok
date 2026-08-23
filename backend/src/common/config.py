"""애플리케이션 설정.

환경변수는 .env.example 을 단일 출처로 삼는다.
새 설정을 추가할 때는 .env.example 에도 함께 반영해야 한다.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# config.py -> common -> src -> backend -> 레포 루트
_BACKEND_DIR = Path(__file__).resolve().parents[2]
_REPO_ROOT = _BACKEND_DIR.parent

# 뒤에 오는 파일이 우선한다.
_ENV_FILES: tuple[Path, ...] = (_REPO_ROOT / ".env", _BACKEND_DIR / ".env")


def loaded_env_files() -> list[Path]:
    """실제로 존재해서 읽히는 .env 경로. 값은 반환하지 않는다.

    pydantic-settings 는 파일 단위가 아니라 키 단위로 병합한다. 루트에 완전한
    .env 가 있어도 backend/.env 에 DATABASE_URL 한 줄만 남아 있으면 그 값이
    이긴다. 두 파일이 섞인 설정이 조용히 만들어지고 어디에도 흔적이 남지
    않으므로, 기동 시 경로만 로그로 남겨 이 상황이 드러나게 한다.
    """
    return [path for path in _ENV_FILES if path.exists()]


class Settings(BaseSettings):
    # env_file 을 상대경로로 두면 실행 위치에 따라 .env 를 못 찾는다. README 는
    # 레포 루트에 .env 를 두라고 안내하는데 API 서버와 pytest 는 backend/ 에서
    # 실행하므로, 그 경우 설정이 조용히 전부 기본값이 된다. 예외가 나지 않고
    # DATABASE_URL 이 빈 문자열이 될 뿐이라 발견이 늦다.
    #
    # 두 위치를 절대경로로 지정해 실행 위치와 무관하게 만든다. 뒤에 오는 파일이
    # 우선하므로 backend/.env 를 따로 둔 사람은 그 값이 루트 .env 를 덮어쓴다.
    model_config = SettingsConfigDict(
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ─── Database ───
    # 반드시 풀링(Pooled) 주소를 사용한다. Direct 주소는 무료 티어의
    # 동시 연결 한도를 금방 초과시킨다.
    #
    # 기본값을 빈 문자열로 두는 이유는 DB가 필요 없는 경로(배치 dry-run,
    # 데이터 생성 스크립트, 단위 테스트)에서도 설정을 읽을 수 있어야 하기
    # 때문이다. 실제 연결 시점에 require_database_url() 로 검증한다.
    database_url: str = Field(default="", alias="DATABASE_URL")
    db_pool_max: int = Field(default=5, alias="DB_POOL_MAX")
    db_pool_timeout_s: int = Field(default=10, alias="DB_POOL_TIMEOUT_S")

    def require_database_url(self) -> str:
        """DB 연결이 필요한 시점에 호출해 설정 누락을 명확히 알린다."""
        if not self.database_url:
            raise RuntimeError(
                "DATABASE_URL 이 설정되지 않았습니다. "
                ".env 를 확인하세요. 풀링(Pooled) 주소를 사용해야 합니다."
            )
        return self.database_url

    # ─── LLM 공통 ───
    llm_provider: Literal["anthropic", "openai", "gemini"] = Field(
        default="anthropic", alias="LLM_PROVIDER"
    )
    llm_api_key: str = Field(default="", alias="LLM_API_KEY")
    llm_model: str = Field(default="", alias="LLM_MODEL")

    # ─── LLM 배치 경로 (약관 변환) ───
    # 사용자가 기다리지 않으므로 넉넉히 잡는다.
    # 실패해도 처리 완료 목록으로 중단 지점부터 재개할 수 있다.
    llm_batch_timeout_ms: int = Field(default=15_000, alias="LLM_BATCH_TIMEOUT_MS")
    llm_batch_max_retry: int = Field(default=5, alias="LLM_BATCH_MAX_RETRY")

    # ─── LLM 런타임 경로 (질의 해석, 결과 설명) ───
    # 동기 응답이므로 재시도 횟수가 아니라 총 소요 시간에 예산을 건다.
    # 예산을 넘기면 재시도 도중이라도 중단하고 대체 응답을 낸다.
    #
    # 횟수 설정을 두지 않는 이유는 stop_after_delay 가 예산만 보기 때문이다.
    # 값을 남겨두면 실제로는 아무 효과가 없는데 바꾸면 동작이 달라진다고
    # 오해하게 된다.
    llm_runtime_timeout_budget_ms: int = Field(
        default=3_500, alias="LLM_RUNTIME_TIMEOUT_BUDGET_MS"
    )

    # ─── App ───
    port: int = Field(default=8000, alias="PORT")
    environment: str = Field(default="development", alias="ENVIRONMENT")
    cors_origin: str = Field(default="http://localhost:5173", alias="CORS_ORIGIN")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """설정을 한 번만 읽어 캐시한다.

    lru_cache 를 쓰는 이유는 매 호출마다 .env 를 다시 파싱하지 않기 위해서다.
    테스트에서 값을 바꿔야 하면 get_settings.cache_clear() 를 호출한다.
    """
    return Settings()  # type: ignore[call-arg]
