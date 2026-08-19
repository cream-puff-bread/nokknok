#!/usr/bin/env python3
"""약관 PDF에서 규칙을 추출해 DB에 적재한다.

1단계 파이프라인이다. 조항을 하나씩 읽으면서 그 자리에서 규칙을 뽑고,
조항과 규칙을 함께 저장한다. 나중에 둘을 다시 매칭할 필요가 없다.

사용법:
    python scripts/ingest_clauses.py --card-id 1 --pdf data/clauses/nokknok-a.pdf
    python scripts/ingest_clauses.py --card-id 1 --pdf ... --dry-run

재개:
    LLM Rate limit 이나 네트워크 문제로 중단되면 처리 완료 목록이
    data/generated/ingest_progress.json 에 남는다. 같은 명령을 다시 실행하면
    처리하지 않은 조항부터 이어서 진행한다.

비용:
    LLM 응답은 캐시에 저장된다. 같은 조항을 다시 호출하지 않으므로
    재실행 시 비용이 들지 않는다. 프롬프트를 수정했다면 --no-cache 를 쓴다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

# 스크립트를 직접 실행할 때 backend/src 를 import 경로에 넣는다.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from sqlalchemy import text  # noqa: E402

from src.common.db import dispose_engine, session_scope  # noqa: E402
from src.common.exceptions import (  # noqa: E402
    ClausePipelineError,
    LlmPermanentError,
    LlmTransientError,
)
from src.common.llm import LlmClient, batch_profile  # noqa: E402
from src.common.logging import get_logger, setup_logging  # noqa: E402
from src.rag.loader import RuleLoader  # noqa: E402
from src.rag.models import Clause  # noqa: E402
from src.rag.pdf_parser import extract_clauses, filter_rule_candidates  # noqa: E402
from src.rag.rule_extractor import RuleExtractor  # noqa: E402

logger = get_logger("ingest_clauses")

PROGRESS_DIR = Path("data/generated")
PROGRESS_FILE = PROGRESS_DIR / "ingest_progress.json"
CACHE_FILE = PROGRESS_DIR / "llm_cache.json"


def clause_key(card_id: int, clause: Clause) -> str:
    """조항을 식별하는 안정적인 키.

    내용 해시를 쓰는 이유는 PDF를 다시 파싱해도 같은 조항이면 같은 키가
    나와야 재개가 가능하기 때문이다. 순번을 쓰면 파싱 결과가 조금만
    달라져도 어긋난다.
    """
    digest = hashlib.sha256(clause.content.encode("utf-8")).hexdigest()[:16]
    return f"{card_id}:{clause.doc_name}:{clause.page_no}:{digest}"


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("%s 를 읽을 수 없어 새로 시작합니다", path.name)
        return {}


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def fetch_card(session, card_id: int) -> tuple[str, str]:
    row = session.execute(
        text("SELECT issuer, name FROM card WHERE id = :id"), {"id": card_id}
    ).first()
    if row is None:
        raise ClausePipelineError(f"카드를 찾을 수 없습니다: id={card_id}")
    return str(row[0]), str(row[1])


class Totals:
    """처리 결과 집계."""

    def __init__(self) -> None:
        self.clauses = 0
        self.benefit = 0
        self.exclusion = 0
        self.dup = 0
        self.empty = 0


def run(
    pending: list[Clause],
    extractor: RuleExtractor,
    cache: dict,
    done: set[str],
    totals: Totals,
    args,
    *,
    loader: RuleLoader | None,
    issuer: str,
    card_name: str,
    session=None,
) -> None:
    """조항을 하나씩 처리한다.

    조항 단위로 커밋하는 이유가 중요하다. 마지막에 한 번만 커밋하면
    중간에 중단됐을 때 진행 상황 파일에는 '완료'로 기록되지만 DB는
    롤백되어, 재실행해도 그 조항을 건너뛰는 상태가 된다.
    조항마다 커밋하고 그 뒤에 done 에 추가하면 두 기록이 어긋나지 않는다.

    조항 수가 수십 건 규모라 커밋 횟수가 성능에 영향을 주지 않는다.
    """
    for idx, clause in enumerate(pending, start=1):
        key = clause_key(args.card_id, clause)
        logger.info("[%d/%d] p.%d 처리 중", idx, len(pending), clause.page_no)

        try:
            if key in cache:
                result = extractor.build_result(clause, cache[key])
                logger.info("  캐시 사용")
            else:
                result = extractor.extract(clause, issuer, card_name)
                cache[key] = _to_cache(result)
        except LlmPermanentError as exc:
            # 인증 오류 등은 재시도해도 소용없다. 즉시 중단한다.
            logger.error("복구 불가능한 오류: %s", exc)
            return
        except LlmTransientError as exc:
            # 재시도를 모두 소진했다. 여기까지의 진행 상황은 유지된다.
            logger.error("재시도 실패, 여기서 중단합니다: %s", exc)
            return

        if result.is_empty:
            totals.empty += 1
            done.add(key)
            continue

        if loader is None:
            _print_result(result)
            done.add(key)
            continue

        report = loader.load(result)
        # 커밋이 성공한 뒤에야 완료로 표시한다. 순서가 뒤바뀌면
        # DB에 없는 조항이 완료로 기록되어 재실행으로도 복구되지 않는다.
        if session is not None:
            session.commit()

        totals.clauses += report.clauses
        totals.benefit += report.benefit_rules
        totals.exclusion += report.exclusion_rules
        totals.dup += report.skipped_duplicate
        done.add(key)


def main() -> int:
    parser = argparse.ArgumentParser(description="약관 PDF 규칙 추출·적재")
    parser.add_argument("--card-id", type=int, required=True)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="DB에 적재하지 않고 추출 결과만 출력",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="LLM 캐시를 무시하고 다시 호출 (프롬프트 수정 후 사용)",
    )
    parser.add_argument(
        "--limit", type=int, default=0, help="처리할 조항 수 제한 (테스트용)"
    )
    args = parser.parse_args()

    setup_logging()

    # ── 1. 조항 추출 ──
    try:
        clauses = extract_clauses(args.pdf)
    except ClausePipelineError as exc:
        logger.error("%s", exc)
        return 1

    candidates = filter_rule_candidates(clauses)
    if args.limit:
        candidates = candidates[: args.limit]
    if not candidates:
        logger.error("규칙 후보 조항이 없습니다")
        return 1

    # ── 2. 진행 상황과 캐시 로드 ──
    progress = load_json(PROGRESS_FILE)
    cache = {} if args.no_cache else load_json(CACHE_FILE)
    done: set[str] = set(progress.get("done", []))

    pending = [c for c in candidates if clause_key(args.card_id, c) not in done]
    logger.info(
        "처리 대상 %d건 (전체 %d건 중 %d건 완료)",
        len(pending),
        len(candidates),
        len(candidates) - len(pending),
    )
    if not pending:
        logger.info("모두 처리되었습니다")
        return 0

    client = LlmClient(batch_profile())
    extractor = RuleExtractor(client)
    totals = Totals()

    try:
        if args.dry_run:
            # dry-run 은 DB 없이 추출 결과만 확인하는 모드다.
            # 세션을 열면 DATABASE_URL 이 없는 환경에서 쓸 수 없다.
            run(pending, extractor, cache, done, totals, args, loader=None,
                issuer="(dry-run)", card_name=f"card_id={args.card_id}")
        else:
            with session_scope() as session:
                issuer, card_name = fetch_card(session, args.card_id)
                loader = RuleLoader(session, args.card_id)
                logger.info("대상 카드: %s %s", issuer, card_name)
                run(pending, extractor, cache, done, totals, args,
                    loader=loader, issuer=issuer, card_name=card_name,
                    session=session)
    finally:
        if not args.dry_run:
            # 배치는 반드시 연결을 명시적으로 해제한다.
            # 남겨두면 API 서버가 붙을 자리를 잠식한다.
            dispose_engine()
        save_json(PROGRESS_FILE, {"done": sorted(done)})
        if not args.no_cache:
            save_json(CACHE_FILE, cache)

    logger.info(
        "완료 — 조항 %d, 혜택규칙 %d, 제외규칙 %d, 중복 %d, 규칙없음 %d",
        totals.clauses,
        totals.benefit,
        totals.exclusion,
        totals.dup,
        totals.empty,
    )
    if not args.dry_run and totals.benefit + totals.exclusion > 0:
        logger.info(
            "적재된 규칙은 verified=false 입니다. "
            "검수 후 true 로 바꿔야 판정에 사용됩니다."
        )
    return 0


def _to_cache(result) -> dict:
    """추출 결과를 캐시 형태로 직렬화한다.

    Decimal 은 JSON 직렬화가 안 되므로 float 로 바꾼다.
    캐시는 재현용이지 판정에 쓰이지 않으므로 정밀도 손실이 문제되지 않는다.
    """
    return {
        "benefit_rules": [
            {
                "perf_min": r.perf_min,
                "perf_max": r.perf_max,
                "category": r.category,
                "discount_rate": float(r.discount_rate),
                "category_cap": r.category_cap,
            }
            for r in result.benefit_rules
        ],
        "exclusion_rules": [
            {
                "exclusion_type": r.exclusion_type.value,
                "target_kind": r.target_kind.value,
                "target_value": r.target_value,
            }
            for r in result.exclusion_rules
        ],
    }


def _print_result(result) -> None:
    print(f"\n--- p.{result.clause.page_no} ---")
    print(result.clause.content[:120].replace("\n", " ") + " ...")
    for r in result.benefit_rules:
        cap = f"{r.category_cap:,}원" if r.category_cap else "한도없음"
        upper = f"{r.perf_max:,}" if r.perf_max else "무제한"
        print(
            f"  혜택 {r.category:<10} {r.discount_rate:>6.2%} "
            f"실적 {r.perf_min:,}~{upper} 한도 {cap}"
        )
    for r in result.exclusion_rules:
        print(f"  제외 {r.exclusion_type.value:<12} {r.target_value}")


if __name__ == "__main__":
    raise SystemExit(main())
