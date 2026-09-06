"""카테고리별 소비 집계 조회.

계산이 아니라 집계다 — 이미 발생한 거래를 카테고리별로 묶어 보여줄 뿐,
가용잔고나 예측처럼 새 값을 만들어내지 않는다.

카테고리 라벨은 하드코딩하지 않는다(CLAUDE.md "No hardcoded enums that
mirror DB data"). transaction.category 는 코드값만 갖고 있어 spend_category
를 조인해야 표시용 라벨을 얻는다.

거래가 없는 카테고리는 결과에 없다. INNER JOIN 이라 그렇다 — spend_category
는 카드 혜택 규칙까지 아우르는 마스터라 계속 늘어날 수 있는데, 매달 전부를
0 으로 채우면 응답 크기가 실제 소비가 아니라 마스터 크기를 따라 커진다
(contracts/api-spec.yaml 의 /api/spending 설명 참조).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.repository import persona as persona_repo

# idx_txn_persona_date (persona_id, txn_date DESC) 를 그대로 타게 ORDER BY ...
# LIMIT 1 로 쓴다. MAX(txn_date) 로 써도 플래너가 같은 계획으로 바꿔주긴
# 하지만, 인덱스가 이미 이 접근 패턴(persona_id 다음 날짜 내림차순)으로
# 만들어져 있으므로 의도를 그대로 드러낸다.
_LAST_TXN_DATE_SQL = text(
    """
    SELECT txn_date
    FROM transaction
    WHERE persona_id = :persona_id AND txn_date <= :ref_date
    ORDER BY txn_date DESC
    LIMIT 1
    """
)

# 월 경계를 반개구간(>= 월초 AND < 다음달초)으로 둔다. EXTRACT나 date_trunc로
# txn_date를 감싸면 idx_txn_persona_date(persona_id, txn_date DESC)를 못 타고
# 전체 스캔이 된다 — 컬럼을 함수로 감싸는 순간 인덱스와 값 형태가 달라지기
# 때문이다. 카테고리 우선순위(전용 > ALL)와 달리 여기는 합산 자체가 목적이라
# 파이썬 루프 대신 윈도우 함수로 총계를 같은 쿼리에서 뽑는다.
#
# month_end 도 여기서 함께 뽑는다 — 그 달의 마지막 거래일이 필요한데, 이미
# 이 쿼리가 그 달의 거래를 전부 들고 있으므로 별도 쿼리를 만들 이유가 없다.
_SPENDING_SQL = text(
    """
    SELECT
        c.code                     AS category,
        c.label                    AS category_label,
        COUNT(t.id)                AS count,
        COALESCE(SUM(t.amount), 0) AS amount,
        SUM(COUNT(t.id))     OVER () AS total_count,
        SUM(SUM(t.amount))   OVER () AS total_amount,
        MAX(MAX(t.txn_date)) OVER () AS month_end
    FROM spend_category c
    JOIN transaction t
      ON t.category = c.code
     AND t.persona_id = :persona_id
     AND t.txn_date >= :range_start
     AND t.txn_date <  :range_end
    GROUP BY c.code, c.label
    ORDER BY amount DESC
    """
)


@dataclass(frozen=True, slots=True)
class SpendingCategory:
    category: str
    category_label: str
    amount: int
    count: int


@dataclass(frozen=True, slots=True)
class SpendingSummary:
    month: str
    month_end: date | None
    total: int
    count: int
    categories: tuple[SpendingCategory, ...]


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end


def _resolve_month(session: Session, persona_id: int, month: str | None, today: date) -> tuple[int, int]:
    if month is not None:
        # API 계층이 이미 YYYY-MM 형식을 검증한다(422). 여기서는 그 보장을
        # 믿고 파싱만 한다.
        parsed = date.fromisoformat(f"{month}-01")
        return parsed.year, parsed.month

    # month 를 생략하면 거래가 있는 마지막 달을 고른다. today(reference_date())
    # 이후 거래는 제외한다 — 기준일이 고정돼 있는데 그 이후 데이터가 섞이면
    # 아직 오지 않은 달이 "마지막 달"로 잡힌다.
    last = session.execute(
        _LAST_TXN_DATE_SQL, {"persona_id": persona_id, "ref_date": today}
    ).scalar_one_or_none()
    last = last or today
    return last.year, last.month


def get_spending_summary(
    session: Session, persona_id: int, month: str | None, today: date
) -> SpendingSummary:
    persona_repo.get_persona_code(session, persona_id)  # 없으면 PersonaNotFoundError

    year, mon = _resolve_month(session, persona_id, month, today)
    range_start, range_end = _month_bounds(year, mon)
    month_label = f"{year:04d}-{mon:02d}"

    rows = session.execute(
        _SPENDING_SQL,
        {"persona_id": persona_id, "range_start": range_start, "range_end": range_end},
    ).all()

    if not rows:
        return SpendingSummary(
            month=month_label, month_end=None, total=0, count=0, categories=()
        )

    categories = tuple(
        SpendingCategory(
            category=r.category,
            category_label=r.category_label,
            amount=r.amount,
            count=r.count,
        )
        for r in rows
    )
    return SpendingSummary(
        month=month_label,
        month_end=rows[0].month_end,
        total=rows[0].total_amount,
        count=rows[0].total_count,
        categories=categories,
    )
