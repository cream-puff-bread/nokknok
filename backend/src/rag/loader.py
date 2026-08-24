"""추출된 규칙을 DB에 적재한다.

1단계 파이프라인의 핵심이 여기에 있다. 조항과 규칙이 한 객체(ExtractionResult)에
함께 들어오므로, 조항을 먼저 INSERT 해 id 를 받고 그 id 를 규칙의 clause_id 로
바로 연결한다. 나중에 규칙과 조항을 다시 매칭할 필요가 없다.

적재된 규칙은 모두 verified=false 다. 사람이 검수해 true 로 바꾸기 전까지는
운영 판정에 쓰이지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.common.logging import get_logger
from src.rag.models import BenefitRule, ExclusionRule, ExtractionResult

logger = get_logger(__name__)


_INSERT_CLAUSE = text(
    """
    INSERT INTO clause_source (card_id, doc_name, page_no, content)
    VALUES (:card_id, :doc_name, :page_no, :content)
    RETURNING id
    """
)

_INSERT_BENEFIT = text(
    """
    INSERT INTO card_benefit_rule
        (card_id, perf_min, perf_max, category, discount_rate,
         category_cap, clause_id, verified)
    VALUES
        (:card_id, :perf_min, :perf_max, :category, :discount_rate,
         :category_cap, :clause_id, false)
    """
)

_INSERT_EXCLUSION = text(
    """
    INSERT INTO card_exclusion
        (card_id, exclusion_type, target_kind, target_value, clause_id, verified)
    VALUES
        (:card_id, :exclusion_type, :target_kind, :target_value, :clause_id, false)
    """
)

_EXISTING_SCOPE = text(
    """
    SELECT perf_min, perf_max, category
    FROM card_benefit_rule
    WHERE card_id = :card_id
    """
)

_EXISTING_EXCLUSION = text(
    """
    SELECT e.exclusion_type, e.target_kind, e.target_value, e.verified,
           c.doc_name, c.page_no, c.content
    FROM card_exclusion e
    LEFT JOIN clause_source c ON c.id = e.clause_id
    WHERE e.card_id = :card_id
    """
)


def _clause_evidence(doc_name: str, page_no: int, content: str) -> dict[str, Any]:
    return {"doc_name": doc_name, "page_no": page_no, "content": content}


@dataclass(frozen=True, slots=True)
class _SeenExclusion:
    """이미 적재된(또는 이번 로더 인스턴스가 방금 적재한) 제외 규칙 대상.

    사전 검사 키(_seen_exclusions)의 값으로 쓴다. 충돌이 나면 이 정보로
    ExclusionConflict의 '기존' 쪽을 채운다.
    """

    exclusion_type: str
    verified: bool
    clause: dict[str, Any] | None


@dataclass(frozen=True, slots=True)
class ExclusionConflict:
    """같은 (target_kind, target_value)에 다른 exclusion_type이 나온 사례.

    uq_exclusion_scope 제약 때문에 신규 값은 DB에 남지 않는다. 사람이
    어느 쪽이 맞는지 판단할 근거(양쪽 조항 원문)를 함께 담아, 호출부가
    파일 등으로 남겨 검수 리포트에서 참조할 수 있게 한다.
    """

    detected_at: str
    card_id: int
    target_kind: str
    target_value: str
    existing_type: str
    existing_verified: bool
    existing_clause: dict[str, Any] | None
    new_type: str
    new_clause: dict[str, Any]


class LoadReport:
    """적재 결과 요약. 검수 대상 규모를 파악하는 데 쓴다.

    skipped_duplicate 와 skipped_conflict 를 분리한 이유: 완전히 같은 행이
    다시 추출된 것(duplicate)과 같은 대상에 다른 exclusion_type이 나온 것
    (conflict)은 성격이 다르다. 전자는 정상이고 조치가 필요 없지만, 후자는
    LLM이 같은 조항을 놓고 모순된 해석을 냈다는 신호라 사람이 반드시 봐야
    한다(docs/decisions/003 id=12 사례). 하나로 합쳐 세면 배치 요약만 보는
    사람은 모순이 발생한 사실 자체를 알 수 없다.
    """

    def __init__(self) -> None:
        self.clauses = 0
        self.benefit_rules = 0
        self.exclusion_rules = 0
        self.skipped_duplicate = 0
        self.skipped_conflict = 0
        self.conflicts: list[ExclusionConflict] = []

    def __str__(self) -> str:
        return (
            f"조항 {self.clauses}건, 혜택규칙 {self.benefit_rules}건, "
            f"제외규칙 {self.exclusion_rules}건, 중복제외 {self.skipped_duplicate}건, "
            f"충돌제외 {self.skipped_conflict}건"
        )


class RuleLoader:
    """조항과 규칙을 함께 적재한다."""

    def __init__(self, session: Session, card_id: int) -> None:
        self._session = session
        self._card_id = card_id
        # uq_rule_scope / uq_exclusion_scope UNIQUE 제약 위반을 미리 걸러내기 위해
        # 기존 키를 읽어둔다. DB에 맡기면 IntegrityError 로 트랜잭션이 깨져
        # 나머지 조항이 날아간다.
        self._seen_scopes = self._load_existing_scopes()
        self._seen_exclusions = self._load_existing_exclusions()

    def load(self, result: ExtractionResult) -> LoadReport:
        """조항 하나와 그 규칙들을 적재한다."""
        report = LoadReport()

        if result.is_empty:
            # 규칙이 없는 조항은 저장하지 않는다.
            # clause_source 는 근거 제시용이므로 근거가 될 규칙이 없으면 불필요하다.
            return report

        clause_id = self._insert_clause(result)
        report.clauses = 1

        for rule in result.benefit_rules:
            if rule.scope_key in self._seen_scopes:
                logger.warning(
                    "중복 규칙 건너뜀 card_id=%d scope=%s", self._card_id, rule.scope_key
                )
                report.skipped_duplicate += 1
                continue
            self._insert_benefit(rule, clause_id)
            self._seen_scopes.add(rule.scope_key)
            report.benefit_rules += 1

        for rule in result.exclusion_rules:
            # uq_exclusion_scope 와 동일한 키다. exclusion_type을 뺀 이유는
            # docs/decisions/003 참조 — 같은 대상에 다른 exclusion_type이
            # 공존하는 것 자체가 막아야 할 충돌이라 키에 넣지 않는다.
            key = (rule.target_kind.value, rule.target_value)
            existing = self._seen_exclusions.get(key)
            if existing is not None:
                if existing.exclusion_type != rule.exclusion_type.value:
                    new_clause = _clause_evidence(
                        result.clause.doc_name, result.clause.page_no, result.clause.content
                    )
                    conflict = ExclusionConflict(
                        detected_at=datetime.now(UTC).isoformat(timespec="seconds"),
                        card_id=self._card_id,
                        target_kind=rule.target_kind.value,
                        target_value=rule.target_value,
                        existing_type=existing.exclusion_type,
                        existing_verified=existing.verified,
                        existing_clause=existing.clause,
                        new_type=rule.exclusion_type.value,
                        new_clause=new_clause,
                    )
                    report.conflicts.append(conflict)
                    # 기존/신규 값을 함께 남겨 어느 쪽이 맞는지 사람이 판단할
                    # 수 있게 한다. 근거 원문은 report.conflicts 쪽에 온전히
                    # 담기므로 로그에는 요약만 남긴다.
                    logger.warning(
                        "제외 규칙 대상 충돌 card_id=%d target=%s "
                        "기존=%s(verified=%s) 신규=%s 신규근거_clause_id=%d — "
                        "신규 건너뜀, 사람 검수 필요",
                        self._card_id,
                        key,
                        existing.exclusion_type,
                        existing.verified,
                        rule.exclusion_type.value,
                        clause_id,
                    )
                    report.skipped_conflict += 1
                else:
                    report.skipped_duplicate += 1
                continue
            self._insert_exclusion(rule, clause_id)
            self._seen_exclusions[key] = _SeenExclusion(
                exclusion_type=rule.exclusion_type.value,
                verified=False,
                clause=_clause_evidence(
                    result.clause.doc_name, result.clause.page_no, result.clause.content
                ),
            )
            report.exclusion_rules += 1

        return report

    # ---------- internal ----------
    def _load_existing_scopes(self) -> set[tuple[int, int | None, str]]:
        rows = self._session.execute(
            _EXISTING_SCOPE, {"card_id": self._card_id}
        ).all()
        return {(r[0], r[1], r[2]) for r in rows}

    def _load_existing_exclusions(self) -> dict[tuple[str, str], _SeenExclusion]:
        rows = self._session.execute(
            _EXISTING_EXCLUSION, {"card_id": self._card_id}
        ).all()
        result: dict[tuple[str, str], _SeenExclusion] = {}
        for exclusion_type, target_kind, target_value, verified, doc_name, page_no, content in rows:
            clause = (
                _clause_evidence(doc_name, page_no, content) if doc_name is not None else None
            )
            result[(target_kind, target_value)] = _SeenExclusion(
                exclusion_type=exclusion_type, verified=verified, clause=clause
            )
        return result

    def _insert_clause(self, result: ExtractionResult) -> int:
        clause = result.clause
        row = self._session.execute(
            _INSERT_CLAUSE,
            {
                "card_id": self._card_id,
                "doc_name": clause.doc_name,
                "page_no": clause.page_no,
                "content": clause.content,
            },
        ).first()
        if row is None:
            raise RuntimeError("조항 INSERT 가 id를 반환하지 않았습니다")
        return int(row[0])

    def _insert_benefit(self, rule: BenefitRule, clause_id: int) -> None:
        try:
            self._session.execute(
                _INSERT_BENEFIT,
                {
                    "card_id": self._card_id,
                    "perf_min": rule.perf_min,
                    "perf_max": rule.perf_max,
                    "category": rule.category,
                    "discount_rate": rule.discount_rate,
                    "category_cap": rule.category_cap,
                    "clause_id": clause_id,
                },
            )
        except IntegrityError:
            # 사전 검사를 통과했는데도 걸렸다면 동시 실행이 원인이다.
            # 배치는 단독 실행이 전제이므로 여기 도달하면 설계를 다시 봐야 한다.
            logger.exception("혜택 규칙 적재 실패 scope=%s", rule.scope_key)
            raise

    def _insert_exclusion(self, rule: ExclusionRule, clause_id: int) -> None:
        try:
            self._session.execute(
                _INSERT_EXCLUSION,
                {
                    "card_id": self._card_id,
                    "exclusion_type": rule.exclusion_type.value,
                    "target_kind": rule.target_kind.value,
                    "target_value": rule.target_value,
                    "clause_id": clause_id,
                },
            )
        except IntegrityError:
            # 사전 검사를 통과했는데도 걸렸다면 동시 실행이 원인이다.
            # 배치는 단독 실행이 전제이므로 여기 도달하면 설계를 다시 봐야 한다.
            logger.exception(
                "제외 규칙 적재 실패 target=%s", (rule.target_kind.value, rule.target_value)
            )
            raise
