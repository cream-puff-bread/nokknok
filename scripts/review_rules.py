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
import json
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

# ingest_clauses.py가 남기는 제외 규칙 충돌 이력. uq_exclusion_scope 제약
# 때문에 충돌한 신규 값은 card_exclusion에 남지 않아, 아래 verified=false
# 조회만으로는 이 사례가 리포트에 보이지 않는다. 파일이 있으면 읽어 반영하고,
# 없으면(아직 충돌이 없었거나 다른 환경) 조용히 건너뛴다.
CONFLICT_LOG_FILE = OUTPUT_DIR / "ingest_exclusion_conflicts.jsonl"

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


def load_conflicts(card_id: int | None) -> list[dict[str, Any]]:
    """ingest_clauses.py가 남긴 제외 규칙 충돌 이력을 읽는다.

    한 줄이 깨져 있어도 나머지 이력을 못 보게 되면 안 되므로, 손상된 줄은
    경고만 남기고 건너뛴다.
    """
    if not CONFLICT_LOG_FILE.exists():
        return []

    records: list[dict[str, Any]] = []
    for line_no, line in enumerate(
        CONFLICT_LOG_FILE.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            logger.warning(
                "%s %d번째 줄을 읽을 수 없어 건너뜁니다", CONFLICT_LOG_FILE.name, line_no
            )
            continue
        if card_id is not None and record.get("card_id") != card_id:
            continue
        records.append(record)
    return records


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


def _conflict_clause_block(clause: dict[str, Any] | None, label: str) -> list[str]:
    if clause is None:
        return [f"- {label}: ⚠ **근거 조항 없음**"]
    content = str(clause["content"]).replace("\n", "\n> ")
    return [
        f"- {label}: {clause['doc_name']} p.{clause['page_no']}",
        "",
        f"> {content}",
    ]


def format_conflict_entry(record: Mapping[str, Any]) -> str:
    """제외 규칙 충돌 하나를 사람이 판단할 수 있는 형태로 조립한다.

    양쪽 근거 조항을 나란히 보여준다 — 어느 exclusion_type이 맞는지는
    코드가 아니라 조항 원문을 읽은 사람만 판단할 수 있다.
    """
    lines = [
        f"#### {record['target_kind']} / {record['target_value']} — "
        f"기존 {record['existing_type']} vs 신규 {record['new_type']} (버려짐)",
        "",
        f"- 발견 시각: {record['detected_at']}",
        f"- 기존 값: **{record['existing_type']}** "
        f"(verified={record['existing_verified']})",
        *_conflict_clause_block(record.get("existing_clause"), "기존 근거"),
        "",
        f"- 신규 값: **{record['new_type']}** (uq_exclusion_scope에 걸려 DB에 저장되지 않음)",
        *_conflict_clause_block(record.get("new_clause"), "신규 근거"),
    ]
    return "\n".join(lines)


def build_markdown(
    benefit_rows: list[Mapping[str, Any]],
    exclusion_rows: list[Mapping[str, Any]],
    *,
    card_id: int | None,
    conflicts: list[dict[str, Any]],
) -> str:
    scope = f"card_id={card_id}" if card_id is not None else "전체 카드"
    lines = [
        f"# 검수 리포트 — {scope}",
        "",
        f"생성 시각: {datetime.now().isoformat(timespec='seconds')}",
        f"대기 건수: 혜택규칙 {len(benefit_rows)}건, 제외규칙 {len(exclusion_rows)}건, "
        f"제외규칙 충돌 {len(conflicts)}건",
        "",
    ]

    cards = sorted(
        {(r["card_id"], r["issuer"], r["card_name"]) for r in benefit_rows}
        | {(r["card_id"], r["issuer"], r["card_name"]) for r in exclusion_rows}
    )
    # 충돌만 있고 검수 대기 규칙은 없는 카드(예: 나머지가 이미 검수 완료된
    # 경우)도 있을 수 있다. 그런 카드는 issuer/card_name을 조회하지 않고도
    # 충돌 이력이 리포트에서 빠지지 않도록 card_id만으로 자리를 만든다.
    known_ids = {c[0] for c in cards}
    for cid in sorted({c["card_id"] for c in conflicts} - known_ids):
        cards.append((cid, "", f"(card_id={cid}, 검수 대기 규칙 없음)"))
    cards.sort()

    if not cards:
        lines.append("검수 대기 규칙이 없습니다.")
        return "\n".join(lines) + "\n"

    for cid, issuer, card_name in cards:
        header = f"{issuer} {card_name}".strip()
        lines.append(f"## {header} (card_id={cid})")
        lines.append("")

        card_benefit = [r for r in benefit_rows if r["card_id"] == cid]
        card_exclusion = [r for r in exclusion_rows if r["card_id"] == cid]
        card_conflicts = [c for c in conflicts if c["card_id"] == cid]

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

        if card_conflicts:
            lines.append("### ⚠ 제외 규칙 충돌 이력")
            lines.append("")
            lines.append(
                "같은 대상에 서로 다른 exclusion_type이 나온 사례다. "
                "uq_exclusion_scope 제약으로 신규 값은 DB에 저장되지 않고 버려졌다. "
                "기존 값이 맞는지 아래 두 근거를 대조해 판단한다(docs/decisions/003)."
            )
            lines.append("")
            for record in card_conflicts:
                lines.append(format_conflict_entry(record))
                lines.append("")

    return "\n".join(lines) + "\n"


# ---------- 콘솔 요약 ----------
def print_summary(
    benefit_rows: list[Mapping[str, Any]],
    exclusion_rows: list[Mapping[str, Any]],
    conflicts: list[dict[str, Any]],
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
        if conflicts:
            print("검수 대기 규칙은 없지만 제외 규칙 충돌 이력이 있습니다.")
        else:
            print("검수 대기 규칙이 없습니다.")
    else:
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

    if conflicts:
        print(
            f"\n⚠ 제외 규칙 충돌 {len(conflicts)}건 — "
            "uq_exclusion_scope에 걸려 DB에는 없지만 사람 검수가 필요합니다. "
            "마크다운 리포트의 '충돌 이력' 섹션을 확인하세요."
        )


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

    # DB 조회와 무관한 파일 읽기라 세션 블록 밖에서 해도 된다.
    conflicts = load_conflicts(args.card_id)

    print_summary(benefit_rows, exclusion_rows, conflicts)

    if not benefit_rows and not exclusion_rows and not conflicts:
        logger.info("검수 대기 규칙이 없어 리포트를 만들지 않습니다.")
        return 0

    label = str(args.card_id) if args.card_id is not None else "all"
    output_path = OUTPUT_DIR / f"review_{label}.md"

    markdown = build_markdown(
        benefit_rows, exclusion_rows, card_id=args.card_id, conflicts=conflicts
    )
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")

    logger.info("리포트 저장: %s", output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
