"""계산의 기준일.

시연 데이터는 특정 시점의 스냅샷이다. `persona.account_balance` 는 계산값이
아니라 시드에 손으로 적은 상수이고, 거래도 그 시점까지만 있다. 그런데 예측은
`date.today()` 를 봤다 — 스냅샷은 멈춰 있는데 계산만 달력을 따라가니 날이
갈수록 둘이 어긋난다.

실제로 페르소나 2 / 200만원 일시불의 보통 시나리오 첫 달 잔고가 이렇게 움직였다.

    2026-09-01   -340,016
    2026-09-05     -8,621
    2026-09-06    +44,728   <- 위기가 사라진다
    2026-09-10 -2,624,877   <- 급여일을 넘기며 290만원이 통째로 빠진다

9/10 의 절벽은 `_income_schedule` 이 급여일을 지났으면 이번 달 급여를 0 으로
두는데, 시드 잔액이 급여 받기 전 금액이라 없는 돈을 빼기 때문이다.

심사는 URL 만 받아 아무 날에나 열어 보는 방식이다. 같은 화면이 여는 날에 따라
"안전" 도 되고 "260만원 부족" 도 되면 안 된다. 그래서 기준일을 시드가 만들어진
시점에 고정한다.
"""

from __future__ import annotations

from datetime import date

from src.common.config import get_settings


def reference_date() -> date:
    """오늘로 삼을 날짜.

    DEMO_TODAY 가 있으면 그 날짜를, 없으면 실제 오늘을 쓴다. 설정을 비우면
    지금까지와 똑같이 동작하므로, 실제 데이터를 붙이는 날 이 값만 지우면 된다.

    벽시계 시각이 필요한 곳(health 의 응답 시각, 수집 시각 기록)에는 쓰지
    않는다. 그건 계산의 기준이 아니라 사건이 실제로 일어난 시각이다.

    **설정은 전역 get_settings() 에서 읽는다. app.state.settings 주입은 이 값에
    영향을 주지 않는다.** create_app(Settings(DEMO_TODAY=...)) 로 넣어도 기준일은
    안 바뀐다는 뜻이다. 이 함수가 어댑터의 FixedExpense 처럼 요청 문맥이 없는
    자리에서도 불리기 때문이고, 그 자리까지 설정을 흘려보내려면 스냅샷 모양을
    바꿔야 한다.

    기준일은 배포 단위로 하나인 값이라 그 대가를 치를 만큼은 아니라고 봤다.
    테스트에서 다른 날짜가 필요하면 둘 중 하나를 쓴다.

    - 계산 함수에 today 를 직접 넘긴다(forecast_cashflow 는 필수 인자다)
    - 이 모듈의 get_settings 를 monkeypatch 한다(tests/test_clock.py 참고)
    """
    return get_settings().demo_today or date.today()
