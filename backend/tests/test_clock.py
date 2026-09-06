"""계산 기준일.

이 파일이 지키는 것은 "DEMO_TODAY 가 실제로 계산에 흘러 들어가는가" 하나다.
설정만 추가해 두고 어느 계산도 그것을 보지 않으면, 배포 환경에 값을 넣어도
화면은 여는 날마다 달라진다 — 그 실패는 조용해서 알아채기 어렵다.
"""

from __future__ import annotations

from datetime import date

import pytest
from src.common import clock
from src.common.config import Settings


def _settings(**kwargs: object) -> Settings:
    return Settings(DATABASE_URL="postgresql://u:p@localhost/db", **kwargs)  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """get_settings 는 lru_cache 라 테스트끼리 값이 새어 나간다."""
    clock.get_settings.cache_clear()
    yield
    clock.get_settings.cache_clear()


def test_DEMO_TODAY가_있으면_그_날짜를_쓴다(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clock, "get_settings", lambda: _settings(DEMO_TODAY="2026-08-20"))

    assert clock.reference_date() == date(2026, 8, 20)


def test_DEMO_TODAY가_없으면_실제_오늘을_쓴다(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clock, "get_settings", lambda: _settings())

    assert clock.reference_date() == date.today()


def test_미사용_구독_판정이_기준일을_따른다(monkeypatch: pytest.MonkeyPatch) -> None:
    """화면 표시용 값이지만 기준일을 따라야 한다.

    시연 데이터가 멈춰 있는데 이 판정만 달력을 따라가면, 날이 갈수록 의심
    구독이 늘어나 어느 날 갑자기 없던 항목이 생긴다.
    """
    from src.adapter.base import ExpenseType, FixedExpense

    sub = FixedExpense(
        expense_type=ExpenseType.SUBSCRIPTION,
        label="영상 스트리밍",
        amount=13_500,
        charge_day=7,
        last_used_date=date(2026, 6, 1),
    )

    # 기준일이 6/1 에서 90일이 안 됐으면 의심하지 않는다.
    monkeypatch.setattr(clock, "get_settings", lambda: _settings(DEMO_TODAY="2026-08-20"))
    assert sub.unused_suspect is False

    # 90일을 넘기면 의심한다. 같은 데이터인데 기준일만 바뀌었다.
    monkeypatch.setattr(clock, "get_settings", lambda: _settings(DEMO_TODAY="2026-09-30"))
    assert sub.unused_suspect is True
