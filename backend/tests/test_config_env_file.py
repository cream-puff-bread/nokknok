"""설정 파일 탐색 경로 회귀 테스트.

env_file 이 상대경로였을 때, README 안내대로 레포 루트에 .env 를 두고
backend/ 에서 서버를 띄우면 설정이 조용히 전부 기본값이 됐다. 예외가 나지
않고 DATABASE_URL 이 빈 문자열이 될 뿐이라 실제 DB 연결을 시도하기 전까지
아무도 알아채지 못한다. 경로가 다시 상대경로로 되돌아가면 여기서 잡는다.
"""

from __future__ import annotations

from pathlib import Path

from src.common.config import Settings, loaded_env_files

# tests -> backend -> 레포 루트
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _env_files() -> list[Path]:
    configured = Settings.model_config["env_file"]
    assert configured is not None
    return [Path(p) for p in configured]


def test_env_file이_절대경로다():
    assert all(p.is_absolute() for p in _env_files())


def test_레포_루트의_env를_읽는다():
    """README 는 레포 루트에 .env 를 두라고 안내한다."""
    assert _REPO_ROOT / ".env" in _env_files()


def test_backend의_env도_읽는다():
    """backend/.env 를 따로 두고 쓰던 사람의 환경이 깨지지 않아야 한다."""
    assert _REPO_ROOT / "backend" / ".env" in _env_files()


def test_읽은_env_경로를_알려준다():
    """pydantic-settings 는 키 단위로 병합한다. 루트에 완전한 .env 가 있어도
    backend/.env 에 일부 키만 남아 있으면 그 키만 덮어써져, 두 파일이 섞인
    설정이 조용히 만들어진다. 기동 로그에 경로를 남기려면 이 값이 필요하다.
    """
    loaded = loaded_env_files()

    assert all(p.exists() for p in loaded)
    assert set(loaded) <= set(_env_files())


def test_env_경로_조회는_값을_노출하지_않는다():
    """반환값은 경로뿐이어야 한다. 값이 섞이면 로그에 자격증명이 남는다."""
    assert all(isinstance(p, Path) for p in loaded_env_files())
