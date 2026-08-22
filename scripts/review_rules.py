#!/usr/bin/env python3
"""검수 대기 규칙(verified=false) 리포트를 생성한다.

카드 3~5종, 조항 수십 개 규모라 화면을 만들 물량이 아니다. 이 스크립트는
verified=false인 card_benefit_rule/card_exclusion을 근거 조항 원문과 나란히
마크다운으로 뽑고, 승인용 UPDATE문을 함께 생성한다.

verified를 이 스크립트가 직접 바꾸지는 않는다. 검수는 사람이 조항 원문을
읽고 판단해야 하는 일이라, 여기서는 판단에 필요한 자료를 모아 보여주는
것까지만 한다. 승인은 출력된 SQL을 사람이 확인하고 직접 실행해야 일어난다.

사용법:
    python scripts/review_rules.py               # 전체 카드
    python scripts/review_rules.py --card-id 1    # 카드 1만
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

# 스크립트를 직접 실행할 때 backend/src 를 import 경로에 넣는다.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from sqlalchemy import text  # noqa: E402

from src.common.db import dispose_engine, session_scope  # noqa: E402
from src.common.logging import get_logger, setup_logging  # noqa: E402

logger = get_logger("review_rules")

OUTPUT_DIR = Path("data/generated")

# clause_id가 NULL이거나 clause_source에서 지워진 행도 검수자가 봐야 하므로
# INNER JOIN이 아니라 LEFT JOIN을 쓴다. INNER JOIN을 쓰면 근거가 없는 규칙이
# 리포트에서 조용히 빠져, 정작 가장 먼저 잡아야 할 문제가 눈에 안 띈다.
_BENEFIT_SQL = """
    SELECT r.id, r.card_id, ca.issuer, ca.name AS card_name,
           r.category, r.discount_rate, r.perf_min, r.perf_max, r.category_cap,
           c.doc_name, c.page_no, c.content
    FROM card_benefit_rule r
    JOIN card ca ON ca.id = r.card_id
    LEFT JOIN clause_source c ON c.id = r.clause_id
    WHERE r.verified = false {card_filter}
    ORDER BY r.card_id, r.perf_min, r.category
"""

_EXCLUSION_SQL = """
    SELECT e.id, e.card_id, ca.issuer, ca.name AS card_name,
           e.exclusion_type, e.target_kind, e.target_value,
           c.doc_name, c.page_no, c.content
    FROM card_exclusion e
    JOIN card ca ON ca.id = e.card_id
    LEFT JOIN clause_source c ON c.id = e.clause_id
    WHERE e.verified = false {card_filter}
    ORDER BY e.card_id, e.exclusion_type, e.target_kind
"""


def fetch_pending(
    session, card_id: int | None
) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]]]:
    """verified=false 혜택규칙·제외규칙을 근거 조항과 함께 조회한다."""
    params = {"card_id": card_id} if card_id is not None else {}

    benefit_filter = "AND r.card_id = :card_id" if card_id is not None else ""
    benefit_rows = (
        session.execute(text(_BENEFIT_SQL.format(card_filter=benefit_filter)), params)
        .mappings()
        .all()
    )

    exclusion_filter = "AND e.card_id = :card_id" if card_id is not None else ""
    exclusion_rows = (
        session.execute(
            text(_EXCLUSION_SQL.format(card_filter=exclusion_filter)), params
        )
        .mappings()
        .all()
    )

    return list(benefit_rows), list(exclusion_rows)


# ---------- 마크다운 조립 ----------
def _clause_block(row: Mapping[str, Any]) -> list[str]:
    if row["content"] is None:
        return ["- ⚠ **근거 조항 없음** (clause_id가 NULL이거나 clause_source에 없음)"]
    content = str(row["content"]).replace("\n", "\n> ")
    return [
        f"- 근거: {row['doc_name']} p.{row['page_no']}",
        "",
        f"> {content}",
    ]


def format_benefit_row(row: Mapping[str, Any]) -> str:
    upper = f"{row['perf_max']:,}" if row["perf_max"] is not None else "무제한"
    cap = (
        f"{row['category_cap']:,}원" if row["category_cap"] is not None else "한도 없음"
    )
    lines = [
        f"#### 혜택규칙 id={row['id']} — {row['category']} "
        f"{float(row['discount_rate']):.2%}",
        "",
        f"- 실적 구간: {row['perf_min']:,} ~ {upper}",
        f"- 카테고리 한도: {cap}",
        *_clause_block(row),
        "",
        "승인 SQL:",
        "```sql",
        f"UPDATE card_benefit_rule SET verified = true WHERE id = {row['id']};",
        "```",
    ]
    return "\n".join(lines)


def format_exclusion_row(row: Mapping[str, Any]) -> str:
    lines = [
        f"#### 제외규칙 id={row['id']} — {row['exclusion_type']} / "
        f"{row['target_kind']} / {row['target_value']}",
        "",
        *_clause_block(row),
        "",
        "승인 SQL:",
        "```sql",
        f"UPDATE card_exclusion SET verified = true WHERE id = {row['id']};",
        "```",
    ]
    return "\n".join(lines)


def build_markdown(
    benefit_rows: list[Mapping[str, Any]],
    exclusion_rows: list[Mapping[str, Any]],
    *,
    card_id: int | None,
) -> str:
    scope = f"card_id={card_id}" if card_id is not None else "전체 카드"
    lines = [
        f"# 검수 리포트 — {scope}",
        "",
        f"생성 시각: {datetime.now().isoformat(timespec='seconds')}",
        f"대기 건수: 혜택규칙 {len(benefit_rows)}건, 제외규칙 {len(exclusion_rows)}건",
        "",
    ]

    cards = sorted(
        {(r["card_id"], r["issuer"], r["card_name"]) for r in benefit_rows}
        | {(r["card_id"], r["issuer"], r["card_name"]) for r in exclusion_rows}
    )

    if not cards:
        lines.append("검수 대기 규칙이 없습니다.")
        return "\n".join(lines) + "\n"

    for cid, issuer, card_name in cards:
        lines.append(f"## {issuer} {card_name} (card_id={cid})")
        lines.append("")

        card_benefit = [r for r in benefit_rows if r["card_id"] == cid]
        card_exclusion = [r for r in exclusion_rows if r["card_id"] == cid]

        if card_benefit:
            lines.append("### 혜택 규칙")
            lines.append("")
            for row in card_benefit:
                lines.append(format_benefit_row(row))
                lines.append("")

        if card_exclusion:
            lines.append("### 제외 규칙")
            lines.append("")
            for row in card_exclusion:
                lines.append(format_exclusion_row(row))
                lines.append("")

    return "\n".join(lines) + "\n"


# ---------- 콘솔 요약 ----------
def print_summary(
    benefit_rows: list[Mapping[str, Any]], exclusion_rows: list[Mapping[str, Any]]
) -> None:
    def _label(row: Mapping[str, Any]) -> tuple[int, str]:
        return row["card_id"], f"{row['issuer']} {row['card_name']}"

    benefit_counts: dict[tuple[int, str], int] = {}
    for row in benefit_rows:
        key = _label(row)
        benefit_counts[key] = benefit_counts.get(key, 0) + 1

    exclusion_counts: dict[tuple[int, str], int] = {}
    for row in exclusion_rows:
        key = _label(row)
        exclusion_counts[key] = exclusion_counts.get(key, 0) + 1

    keys = sorted(set(benefit_counts) | set(exclusion_counts))
    if not keys:
        print("검수 대기 규칙이 없습니다.")
        return

    print(f"\n{'카드':<28} {'혜택규칙':>8} {'제외규칙':>8} {'합계':>6}")
    print("-" * 54)
    total_b = total_e = 0
    for card_id, label in keys:
        b = benefit_counts.get((card_id, label), 0)
        e = exclusion_counts.get((card_id, label), 0)
        total_b += b
        total_e += e
        print(f"{label:<28} {b:>8} {e:>8} {b + e:>6}")
    print("-" * 54)
    print(f"{'합계':<28} {total_b:>8} {total_e:>8} {total_b + total_e:>6}")


def main() -> int:
    parser = argparse.ArgumentParser(description="검수 대기 규칙 리포트 생성")
    parser.add_argument(
        "--card-id", type=int, default=None, help="대상 카드. 생략하면 전체 카드"
    )
    args = parser.parse_args()

    setup_logging()

    try:
        with session_scope() as session:
            benefit_rows, exclusion_rows = fetch_pending(session, args.card_id)
    finally:
        # 배치는 작업이 끝나면 연결을 명시적으로 해제한다.
        # 남겨두면 API 서버가 붙을 자리를 잠식한다.
        dispose_engine()

    print_summary(benefit_rows, exclusion_rows)

    if not benefit_rows and not exclusion_rows:
        logger.info("검수 대기 규칙이 없어 리포트를 만들지 않습니다.")
        return 0

    label = str(args.card_id) if args.card_id is not None else "all"
    output_path = OUTPUT_DIR / f"review_{label}.md"

    markdown = build_markdown(benefit_rows, exclusion_rows, card_id=args.card_id)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")

    logger.info("리포트 저장: %s", output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
