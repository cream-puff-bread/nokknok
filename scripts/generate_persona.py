#!/usr/bin/env python3
"""페르소나별 가상 거래 내역을 생성한다.

6개월치를 손으로 만드는 것은 불가능하므로 스크립트로 생성한다.
균일 난수로 만들면 카테고리별 변동성이 사라져 예측 모듈의 분위수 밴드가 항상
좁게 나오고, 밴드가 제 역할을 하는지 확인할 방법이 없어진다.

반영한 패턴:
  - 요일 효과: 주말에 외식·문화 지출이 늘어난다
  - 월중 효과: 급여일 직후 소비가 몰린다
  - 카테고리별 변동성: 식비는 잦고 작게, 쇼핑은 드물고 크게
  - 일회성 대형 지출: 몇 달에 한 번 여행이나 가전 구매가 섞인다

이 중 예측 모듈이 실제로 쓰는 것은 뒤의 둘이다. 응답 단위가 월말 잔고라 요일
효과는 한 달 안에서 상쇄되고, 월별 계절 효과는 같은 달을 두 번 이상 관측해야
추세와 분리되는데 6개월로는 불가능하다. 앞의 둘은 데이터를 실제 소비처럼
보이게 하려고 넣는다(docs/decisions/005-forecast-baseline.md 6절).

사용법:
    python scripts/generate_persona.py --months 6
    python scripts/generate_persona.py --months 6 --persona SUBSCRIPTION_HEAVY
    python scripts/generate_persona.py --months 6 --output data/generated/txn.sql
    python scripts/generate_persona.py --months 6 --seed 42   # 재현 가능
"""

from __future__ import annotations

import argparse
import random
import sys
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from faker import Faker  # noqa: E402

from src.common.logging import get_logger, setup_logging  # noqa: E402

logger = get_logger("generate_persona")
fake = Faker("ko_KR")


# ─────────────────────────────────────────────
# 카테고리별 소비 특성
# ─────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class CategoryProfile:
    """한 카테고리의 소비 특성.

    monthly_count 는 월 결제 횟수, amount 범위는 1회 결제액이다.
    weekend_boost 가 1보다 크면 주말에 더 자주 결제한다.
    """

    code: str
    monthly_count: tuple[int, int]
    amount: tuple[int, int]
    merchants: tuple[str, ...]
    weekend_boost: float = 1.0
    payday_boost: float = 1.0


CATEGORY_PROFILES: tuple[CategoryProfile, ...] = (
    CategoryProfile(
        "DINING", (12, 22), (8_000, 45_000),
        ("김밥천국", "본죽", "한솥도시락", "역전우동", "명륜진사갈비",
         "홍콩반점", "새마을식당", "백종원의원조쌈밥집"),
        weekend_boost=1.6, payday_boost=1.3,
    ),
    CategoryProfile(
        "CAFE", (8, 18), (3_500, 9_000),
        ("스타벅스", "투썸플레이스", "메가커피", "컴포즈커피",
         "이디야커피", "빽다방"),
        weekend_boost=1.2,
    ),
    CategoryProfile(
        "DELIVERY", (4, 12), (15_000, 38_000),
        ("배달앱 결제", "요기요", "쿠팡이츠"),
        weekend_boost=2.0,
    ),
    CategoryProfile(
        "GROCERY", (3, 7), (25_000, 90_000),
        ("이마트", "홈플러스", "롯데마트", "GS더프레시"),
        weekend_boost=1.8,
    ),
    CategoryProfile(
        "ONLINE", (4, 10), (12_000, 150_000),
        ("쿠팡", "네이버페이", "11번가", "무신사", "올리브영온라인"),
        payday_boost=1.7,
    ),
    CategoryProfile(
        "TRANSPORT", (15, 28), (1_400, 8_000),
        ("교통카드 충전", "카카오T", "티머니"),
        weekend_boost=0.7,
    ),
    CategoryProfile(
        "CULTURE", (1, 4), (12_000, 60_000),
        ("CGV", "메가박스", "예스24", "교보문고"),
        weekend_boost=2.2,
    ),
    CategoryProfile(
        "MEDICAL", (0, 2), (5_000, 45_000),
        ("연세이비인후과", "미소치과", "온누리약국"),
    ),
    CategoryProfile(
        "TELECOM", (1, 1), (35_000, 65_000),
        ("통신요금 자동이체",),
    ),
)

# 몇 달에 한 번 발생하는 대형 지출.
# 이동평균만 쓰면 이런 지출이 평균을 끌어올려 예측이 왜곡된다.
# 중앙값을 함께 쓰는 이유를 검증하기 위해 의도적으로 포함한다.
OCCASIONAL_EXPENSES: tuple[tuple[str, str, int, int], ...] = (
    ("ONLINE", "가전 구매", 350_000, 900_000),
    ("CULTURE", "여행 예약", 200_000, 600_000),
    ("ONLINE", "의류 대량 구매", 150_000, 400_000),
)

# 페르소나별 소비 강도 배율
PERSONA_SCALE: dict[str, float] = {
    "SUBSCRIPTION_HEAVY": 0.85,  # 구독에 이미 많이 나가 변동 지출은 적은 편
    "INSTALLMENT_HEAVY": 0.75,   # 할부 상환 부담으로 소비를 줄인 상태
    "STABLE": 1.15,              # 여유가 있어 소비 여력이 크다
}


def month_starts(months: int, end: date | None = None) -> list[date]:
    """최근 N개월의 1일 목록을 오래된 순으로 반환한다."""
    anchor = end or date.today()
    result: list[date] = []
    year, month = anchor.year, anchor.month
    for _ in range(months):
        result.append(date(year, month, 1))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return sorted(result)


def pick_day(
    year: int, month: int, profile: CategoryProfile, income_day: int, rng: random.Random
) -> date:
    """요일 효과와 급여일 효과를 반영해 결제일을 고른다.

    가중치를 계산해 뽑는다. 균등 분포로 뽑으면 예측 모듈이 검증할
    계절성 자체가 데이터에 없게 된다.
    """
    last_day = monthrange(year, month)[1]
    weights: list[float] = []

    for day in range(1, last_day + 1):
        d = date(year, month, day)
        w = 1.0
        if d.weekday() >= 5:
            w *= profile.weekend_boost
        # 급여일부터 5일간 소비가 늘어난다
        if 0 <= (day - income_day) < 5:
            w *= profile.payday_boost
        weights.append(w)

    day = rng.choices(range(1, last_day + 1), weights=weights, k=1)[0]
    return date(year, month, day)


def generate_transactions(
    persona_id: int,
    persona_code: str,
    card_ids: list[int],
    income_day: int,
    months: int,
    rng: random.Random,
) -> list[dict]:
    """한 페르소나의 거래 내역을 생성한다."""
    scale = PERSONA_SCALE.get(persona_code, 1.0)
    rows: list[dict] = []
    today = date.today()

    for start in month_starts(months):
        for profile in CATEGORY_PROFILES:
            low, high = profile.monthly_count
            count = round(rng.randint(low, high) * scale)

            for _ in range(count):
                txn_date = pick_day(
                    start.year, start.month, profile, income_day, rng
                )
                if txn_date > today:
                    continue

                amount = rng.randint(*profile.amount)
                # 끝자리를 다듬어 실제 결제액처럼 보이게 한다
                amount = amount - (amount % 10)

                rows.append(
                    {
                        "persona_id": persona_id,
                        "card_id": rng.choice(card_ids) if card_ids else None,
                        "txn_date": txn_date,
                        "merchant": rng.choice(profile.merchants),
                        "amount": amount,
                        "category": profile.code,
                        "payment_type": "LUMP",
                        "installment_months": 0,
                        "is_recurring": profile.code == "TELECOM",
                    }
                )

        # 대형 지출은 25% 확률로 월 1회 발생한다
        if rng.random() < 0.25:
            category, label, low, high = rng.choice(OCCASIONAL_EXPENSES)
            txn_date = pick_day(
                start.year,
                start.month,
                CATEGORY_PROFILES[0],
                income_day,
                rng,
            )
            if txn_date <= today:
                amount = rng.randint(low, high)
                # 30만원 이상은 할부로 결제하는 경우가 많다
                months_opt = rng.choice([0, 3, 6]) if amount >= 300_000 else 0
                rows.append(
                    {
                        "persona_id": persona_id,
                        "card_id": rng.choice(card_ids) if card_ids else None,
                        "txn_date": txn_date,
                        "merchant": label,
                        "amount": amount - (amount % 100),
                        "category": category,
                        "payment_type": (
                            "INSTALLMENT" if months_opt else "LUMP"
                        ),
                        "installment_months": months_opt,
                        "is_recurring": False,
                    }
                )

    rows.sort(key=lambda r: r["txn_date"])
    return rows


def to_sql(rows: list[dict]) -> str:
    """INSERT 문으로 변환한다.

    psycopg 파라미터 바인딩 대신 SQL 파일로 내보내는 이유는,
    팀원이 psql 로 바로 적재할 수 있고 결과를 눈으로 검토할 수 있기 때문이다.
    """
    lines = [
        "-- 자동 생성된 거래 내역. 직접 수정하지 말고 스크립트를 다시 실행할 것.",
        "-- scripts/generate_persona.py",
        "",
        "INSERT INTO transaction",
        "    (persona_id, card_id, txn_date, merchant, amount, category,",
        "     payment_type, installment_months, is_recurring)",
        "VALUES",
    ]

    values: list[str] = []
    for r in rows:
        card = str(r["card_id"]) if r["card_id"] is not None else "NULL"
        merchant = r["merchant"].replace("'", "''")
        values.append(
            f"({r['persona_id']}, {card}, '{r['txn_date']}', '{merchant}', "
            f"{r['amount']}, '{r['category']}', '{r['payment_type']}', "
            f"{r['installment_months']}, {str(r['is_recurring']).lower()})"
        )

    lines.append(",\n".join(values) + ";")
    return "\n".join(lines) + "\n"


def print_summary(persona_code: str, rows: list[dict]) -> None:
    """생성 결과를 요약한다. 값이 현실적인지 눈으로 확인하는 용도다."""
    if not rows:
        return
    by_month: dict[str, int] = {}
    by_category: dict[str, int] = {}
    for r in rows:
        key = r["txn_date"].strftime("%Y-%m")
        by_month[key] = by_month.get(key, 0) + r["amount"]
        by_category[r["category"]] = by_category.get(r["category"], 0) + r["amount"]

    print(f"\n[{persona_code}] 거래 {len(rows)}건")
    print("  월별 지출")
    for month, total in sorted(by_month.items()):
        print(f"    {month}  {total:>12,}원")
    print("  카테고리별 합계 (상위 5)")
    for cat, total in sorted(by_category.items(), key=lambda x: -x[1])[:5]:
        print(f"    {cat:<12} {total:>12,}원")


# 시드 데이터와 일치해야 한다. data/personas.seed.sql 참조.
PERSONA_FIXTURES: tuple[tuple[int, str, list[int], int], ...] = (
    (1, "SUBSCRIPTION_HEAVY", [1, 3], 25),
    (2, "INSTALLMENT_HEAVY", [1, 2, 3], 10),
    (3, "STABLE", [1, 2, 3], 25),
)


def main() -> int:
    parser = argparse.ArgumentParser(description="가상 거래 내역 생성")
    parser.add_argument("--months", type=int, default=6)
    parser.add_argument(
        "--persona", type=str, default="", help="특정 페르소나만 생성"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/generated/transactions.sql"),
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="난수 시드. 지정하면 매번 같은 결과가 나온다",
    )
    args = parser.parse_args()

    setup_logging()
    rng = random.Random(args.seed)
    if args.seed is not None:
        Faker.seed(args.seed)

    targets = [
        f for f in PERSONA_FIXTURES if not args.persona or f[1] == args.persona
    ]
    if not targets:
        logger.error("해당 페르소나를 찾을 수 없습니다: %s", args.persona)
        return 1

    all_rows: list[dict] = []
    for persona_id, code, card_ids, income_day in targets:
        rows = generate_transactions(
            persona_id, code, card_ids, income_day, args.months, rng
        )
        print_summary(code, rows)
        all_rows.extend(rows)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(to_sql(all_rows), encoding="utf-8")

    logger.info("생성 완료 rows=%d → %s", len(all_rows), args.output)
    logger.info("적재: psql $DATABASE_URL -f %s", args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
