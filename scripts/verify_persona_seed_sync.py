#!/usr/bin/env python3
"""data/personas.seed.sql 과 실제 DB의 persona/fixed_expense 정합성을 검증한다.

작업 브랜치가 main보다 뒤처진 상태에서 seed 파일을 근거로 판단하면
이미 반영된 DB 값과 달라 보여 잘못된 결론으로 이어질 수 있다. 사람이
두 값을 눈으로 대조하는 대신 기계적으로 확인해 이런 착시를 바로 드러낸다.

seed 파일을 직접 실행해 비교하지 않는 이유는 INSERT에 ON CONFLICT가 없어
재실행하면 행이 중복되기 때문이다. 대신 파일을 파싱해 기대값을 뽑아
DB 조회 결과와 비교한다.

사용법:
    python scripts/verify_persona_seed_sync.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from sqlalchemy import text  # noqa: E402

from src.common.db import dispose_engine, session_scope  # noqa: E402
from src.common.logging import get_logger, setup_logging  # noqa: E402

logger = get_logger("verify_persona_seed_sync")

SEED_FILE = Path(__file__).resolve().parent.parent / "data" / "personas.seed.sql"

_INSERT_RE = re.compile(r"INSERT INTO (\w+)\s*\(([^)]*)\)\s*VALUES\s*(.*)", re.DOTALL)


def _split_top_level(fields: str) -> list[str]:
    """따옴표 안의 콤마는 무시하고 최상위 콤마로만 나눈다."""
    parts: list[str] = []
    buf: list[str] = []
    in_quote = False
    i = 0
    while i < len(fields):
        ch = fields[i]
        if ch == "'":
            if in_quote and i + 1 < len(fields) and fields[i + 1] == "'":
                buf.append("''")
                i += 2
                continue
            in_quote = not in_quote
            buf.append(ch)
        elif ch == "," and not in_quote:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
        i += 1
    parts.append("".join(buf))
    return [p.strip() for p in parts]


def _extract_tuples(values_block: str) -> list[str]:
    """VALUES 블록에서 최상위 괄호로 묶인 튜플들의 내용을 추출한다."""
    tuples: list[str] = []
    depth = 0
    buf: list[str] = []
    in_quote = False
    i = 0
    while i < len(values_block):
        ch = values_block[i]
        if ch == "'":
            if in_quote and i + 1 < len(values_block) and values_block[i + 1] == "'":
                buf.append("''")
                i += 2
                continue
            in_quote = not in_quote
            buf.append(ch)
        elif ch == "(" and not in_quote:
            depth += 1
            if depth > 1:
                buf.append(ch)
        elif ch == ")" and not in_quote:
            depth -= 1
            if depth == 0:
                tuples.append("".join(buf))
                buf = []
            else:
                buf.append(ch)
        elif depth >= 1:
            buf.append(ch)
        i += 1
    return tuples


def _sql_literal(raw: str) -> Any:
    raw = raw.strip()
    if raw.upper() == "NULL":
        return None
    if raw.startswith("'") and raw.endswith("'"):
        return raw[1:-1].replace("''", "'")
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    return raw


def parse_seed(path: Path) -> tuple[dict[int, dict[str, Any]], dict[int, tuple[int, int]]]:
    """personas.seed.sql 을 파싱해 persona 기대값과 fixed_expense 집계를 뽑는다.

    반환: (persona_id -> {account_balance, monthly_income, income_day},
           persona_id -> (건수, 금액합계))
    """
    content = path.read_text(encoding="utf-8")
    personas: dict[int, dict[str, Any]] = {}
    fixed_rows: list[dict[str, Any]] = []

    for stmt in content.split(";"):
        stmt = stmt.strip()
        # 각 INSERT 앞에 섹션 설명 주석이 붙어 있어 match()로는 못 잡는다.
        match = _INSERT_RE.search(stmt)
        if match is None:
            continue
        table, columns_raw, values_block = match.groups()
        columns = [c.strip() for c in columns_raw.split(",")]

        for tuple_str in _extract_tuples(values_block):
            fields = _split_top_level(tuple_str)
            row = dict(zip(columns, (_sql_literal(f) for f in fields)))
            if table == "persona":
                personas[row["id"]] = {
                    "account_balance": row["account_balance"],
                    "monthly_income": row["monthly_income"],
                    "income_day": row["income_day"],
                }
            elif table == "fixed_expense":
                fixed_rows.append(row)

    fixed_agg: dict[int, tuple[int, int]] = {}
    for row in fixed_rows:
        pid = row["persona_id"]
        count, total = fixed_agg.get(pid, (0, 0))
        fixed_agg[pid] = (count + 1, total + row["amount"])

    return personas, fixed_agg


def fetch_db_state(session) -> tuple[dict[int, dict[str, Any]], dict[int, tuple[int, int]]]:
    persona_rows = session.execute(
        text("SELECT id, account_balance, monthly_income, income_day FROM persona ORDER BY id")
    ).all()
    personas = {
        row.id: {
            "account_balance": row.account_balance,
            "monthly_income": row.monthly_income,
            "income_day": row.income_day,
        }
        for row in persona_rows
    }

    fixed_rows = session.execute(
        text(
            "SELECT persona_id, COUNT(*), COALESCE(SUM(amount), 0) "
            "FROM fixed_expense GROUP BY persona_id"
        )
    ).all()
    fixed_agg = {row[0]: (row[1], row[2]) for row in fixed_rows}
    return personas, fixed_agg


def compare(
    seed_personas: dict[int, dict[str, Any]],
    seed_fixed: dict[int, tuple[int, int]],
    db_personas: dict[int, dict[str, Any]],
    db_fixed: dict[int, tuple[int, int]],
) -> list[str]:
    mismatches: list[str] = []
    persona_ids = sorted(set(seed_personas) | set(db_personas))

    for pid in persona_ids:
        seed_row = seed_personas.get(pid)
        db_row = db_personas.get(pid)
        if seed_row is None:
            mismatches.append(f"persona {pid}: seed에 없음 (DB에는 존재)")
            continue
        if db_row is None:
            mismatches.append(f"persona {pid}: DB에 없음 (seed에는 존재)")
            continue
        for field in ("account_balance", "monthly_income", "income_day"):
            if seed_row[field] != db_row[field]:
                mismatches.append(
                    f"persona {pid}.{field}: seed={seed_row[field]:,} "
                    f"DB={db_row[field]:,}"
                )

        seed_count, seed_sum = seed_fixed.get(pid, (0, 0))
        db_count, db_sum = db_fixed.get(pid, (0, 0))
        if seed_count != db_count or seed_sum != db_sum:
            mismatches.append(
                f"persona {pid}.fixed_expense: seed=(건수 {seed_count}, 합계 {seed_sum:,}) "
                f"DB=(건수 {db_count}, 합계 {db_sum:,})"
            )

    return mismatches


def print_report(
    seed_personas: dict[int, dict[str, Any]],
    seed_fixed: dict[int, tuple[int, int]],
    db_personas: dict[int, dict[str, Any]],
    db_fixed: dict[int, tuple[int, int]],
) -> None:
    persona_ids = sorted(set(seed_personas) | set(db_personas))
    header = f"{'id':>3} {'항목':<16} {'seed':>14} {'DB':>14} {'일치':>4}"
    print(header)
    print("-" * len(header))
    for pid in persona_ids:
        seed_row = seed_personas.get(pid, {})
        db_row = db_personas.get(pid, {})
        for field in ("account_balance", "monthly_income", "income_day"):
            sval = seed_row.get(field)
            dval = db_row.get(field)
            ok = "OK" if sval == dval else "X"
            print(
                f"{pid:>3} {field:<16} "
                f"{('-' if sval is None else f'{sval:,}'):>14} "
                f"{('-' if dval is None else f'{dval:,}'):>14} {ok:>4}"
            )
        s_count, s_sum = seed_fixed.get(pid, (0, 0))
        d_count, d_sum = db_fixed.get(pid, (0, 0))
        ok = "OK" if (s_count, s_sum) == (d_count, d_sum) else "X"
        print(
            f"{pid:>3} {'fixed_expense 합계':<16} "
            f"{s_sum:>14,} {d_sum:>14,} {ok:>4} (건수 {s_count} vs {d_count})"
        )


def main() -> int:
    setup_logging()

    if not SEED_FILE.exists():
        logger.error("seed 파일을 찾을 수 없습니다: %s", SEED_FILE)
        return 1

    seed_personas, seed_fixed = parse_seed(SEED_FILE)

    try:
        with session_scope() as session:
            db_personas, db_fixed = fetch_db_state(session)
    finally:
        dispose_engine()

    print_report(seed_personas, seed_fixed, db_personas, db_fixed)
    mismatches = compare(seed_personas, seed_fixed, db_personas, db_fixed)

    if mismatches:
        print(f"\n불일치 {len(mismatches)}건:")
        for m in mismatches:
            print(f"  - {m}")
        return 1

    print("\n모든 페르소나가 seed와 DB에서 일치합니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
