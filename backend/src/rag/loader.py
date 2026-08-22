"""추출된 규칙을 DB에 적재한다.

1단계 파이프라인의 핵심이 여기에 있다. 조항과 규칙이 한 객체(ExtractionResult)에
함께 들어오므로, 조항을 먼저 INSERT 해 id 를 받고 그 id 를 규칙의 clause_id 로
바로 연결한다. 나중에 규칙과 조항을 다시 매칭할 필요가 없다.

적재된 규칙은 모두 verified=false 다. 사람이 검수해 true 로 바꾸기 전까지는
운영 판정에 쓰이지 않는다.
"""

from __future__ import annotations

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
    SELECT exclusion_type, target_kind, target_value
    FROM card_exclusion
    WHERE card_id = :card_id
    """
)


class LoadReport:
    """적재 결과 요약. 검수 대상 규모를 파악하는 데 쓴다."""

    def __init__(self) -> None:
        self.clauses = 0
        self.benefit_rules = 0
        self.exclusion_rules = 0
        self.skipped_duplicate = 0

    def __str__(self) -> str:
        return (
            f"조항 {self.clauses}건, 혜택규칙 {self.benefit_rules}건, "
            f"제외규칙 {self.exclusion_rules}건, 중복제외 {self.skipped_duplicate}건"
        )


class RuleLoader:
    """조항과 규칙을 함께 적재한다."""

    def __init__(self, session: Session, card_id: int) -> None:
        self._session = session
        self._card_id = card_id
        # uq_rule_scope UNIQUE 제약 위반을 미리 걸러내기 위해 기존 키를 읽어둔다.
        # DB에 맡기면 IntegrityError 로 트랜잭션이 깨져 나머지 조항이 날아간다.
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
            key = (rule.exclusion_type.value, rule.target_kind.value, rule.target_value)
            if key in self._seen_exclusions:
                report.skipped_duplicate += 1
                continue
            self._insert_exclusion(rule, clause_id)
            self._seen_exclusions.add(key)
            report.exclusion_rules += 1

        return report

    # ---------- internal ----------
    def _load_existing_scopes(self) -> set[tuple[int, int | None, str]]:
        rows = self._session.execute(
            _EXISTING_SCOPE, {"card_id": self._card_id}
        ).all()
        return {(r[0], r[1], r[2]) for r in rows}

    def _load_existing_exclusions(self) -> set[tuple[str, str, str]]:
        rows = self._session.execute(
            _EXISTING_EXCLUSION, {"card_id": self._card_id}
        ).all()
        return {(r[0], r[1], r[2]) for r in rows}

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
