"""RuleLoader 통합 테스트.

단위 테스트(test_rag.py)는 RuleExtractor(LLM 호출부)만 스텁으로 검증한다.
RuleLoader는 실제 INSERT와 RETURNING, FK 연결, UNIQUE 사전 검사가 핵심이므로
실제 DB 없이는 의미 있게 검증할 수 없다.

카드 1(NOKKNOK A)은 data/cards.seed.sql로 이미 (300000, 500000, 'DINING')
규칙을 갖고 있다. 이 파일은 그 시드를 전제로 중복 검사를 검증하고, 모든 테스트는
db_session 트랜잭션 안에서만 INSERT하고 끝나면 롤백하므로 시드 데이터나 이후
테스트 실행에 영향을 남기지 않는다.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from src.rag.loader import RuleLoader
from src.rag.models import (
    BenefitRule,
    Clause,
    ExclusionRule,
    ExclusionType,
    ExtractionResult,
    TargetKind,
)

pytestmark = pytest.mark.integration

CARD_A_ID = 1  # data/cards.seed.sql: NOKKNOK A (계단형)


def _result(
    benefit_rules: list[BenefitRule],
    *,
    content: str,
    exclusion_rules: list[ExclusionRule] | None = None,
) -> ExtractionResult:
    return ExtractionResult(
        clause=Clause(doc_name="통합테스트.pdf", page_no=1, content=content),
        benefit_rules=benefit_rules,
        exclusion_rules=exclusion_rules or [],
    )


class TestClauseInsertReturningId:
    def test_clause_INSERT는_RETURNING으로_실제_id를_반환하고_규칙에_연결된다(
        self, db_session
    ):
        loader = RuleLoader(db_session, card_id=CARD_A_ID)
        result = _result(
            [
                BenefitRule(
                    perf_min=900_000,
                    perf_max=None,
                    category="MEDICAL",
                    discount_rate=Decimal("0.05"),
                    category_cap=5_000,
                )
            ],
            content="통합 테스트용 신규 조항 - MEDICAL 5%",
        )

        report = loader.load(result)

        assert report.clauses == 1
        assert report.benefit_rules == 1
        assert report.skipped_duplicate == 0

        row = db_session.execute(
            text(
                """
                SELECT clause_id FROM card_benefit_rule
                WHERE card_id = :card_id AND category = 'MEDICAL' AND perf_min = 900000
                """
            ),
            {"card_id": CARD_A_ID},
        ).first()
        assert row is not None
        clause_id = row[0]
        # clause_id가 NULL이면 RETURNING id가 규칙에 전달되지 않은 것이다.
        assert clause_id is not None

        clause_row = db_session.execute(
            text("SELECT content FROM clause_source WHERE id = :id"),
            {"id": clause_id},
        ).first()
        assert clause_row is not None
        assert clause_row[0] == "통합 테스트용 신규 조항 - MEDICAL 5%"


class TestUniqueScopePreCheck:
    def test_기존_규칙과_scope가_겹치면_사전검사에서_걸러진다(self, db_session):
        # 카드 1은 시드에서 이미 (300000, 500000, 'DINING')을 가지고 있다.
        loader = RuleLoader(db_session, card_id=CARD_A_ID)
        result = _result(
            [
                BenefitRule(
                    perf_min=300_000,
                    perf_max=500_000,
                    category="DINING",
                    discount_rate=Decimal("0.99"),  # 겹치면 이 값은 절대 들어가면 안 된다
                )
            ],
            content="중복 시도용 조항",
        )

        report = loader.load(result)

        # is_empty 판정은 규칙 유무만 보므로 조항 자체는 적재되지만,
        # 중복 규칙은 세이브되지 않는다.
        assert report.clauses == 1
        assert report.benefit_rules == 0
        assert report.skipped_duplicate == 1

        rows = db_session.execute(
            text(
                """
                SELECT discount_rate FROM card_benefit_rule
                WHERE card_id = :card_id AND perf_min = 300000
                  AND perf_max = 500000 AND category = 'DINING'
                """
            ),
            {"card_id": CARD_A_ID},
        ).all()
        # 시드의 기존 행 하나만 존재해야 한다. 0.99가 섞여 들어갔다면 중복이 새어나간 것이다.
        assert len(rows) == 1
        assert rows[0][0] != Decimal("0.99")

    def test_같은_로더_인스턴스_안에서_적재한_규칙도_다음_load_호출에서_중복_처리된다(
        self, db_session
    ):
        # 새 scope(perf_min=950000)로 먼저 적재한 뒤, 같은 로더로 다시 같은
        # scope를 적재하면 in-memory _seen_scopes가 갱신돼 있어야 걸러진다.
        loader = RuleLoader(db_session, card_id=CARD_A_ID)
        first = _result(
            [
                BenefitRule(
                    perf_min=950_000,
                    perf_max=None,
                    category="CULTURE",
                    discount_rate=Decimal("0.03"),
                )
            ],
            content="첫 적재",
        )
        second = _result(
            [
                BenefitRule(
                    perf_min=950_000,
                    perf_max=None,
                    category="CULTURE",
                    discount_rate=Decimal("0.90"),
                )
            ],
            content="같은 scope 재시도",
        )

        report1 = loader.load(first)
        report2 = loader.load(second)

        assert report1.benefit_rules == 1
        assert report1.skipped_duplicate == 0
        assert report2.benefit_rules == 0
        assert report2.skipped_duplicate == 1


class TestUniqueExclusionPreCheck:
    """docs/decisions/003 id=12 재현 방지 회귀 테스트.

    카드 1은 시드에서 이미 (PERFORMANCE, CATEGORY, TAX)를 가지고 있다. 같은
    대상(CATEGORY/TAX)에 다른 exclusion_type(BOTH)을 적재하려 하면 — 실제로
    LLM이 두 번째 호출에서 잘못 분류해 발생했던 상황 — uq_exclusion_scope와
    동일한 사전 검사 키가 이를 걸러내야 한다.

    이 클래스는 또한 skipped_duplicate/skipped_conflict 분리를 검증한다.
    완전히 같은 행이 다시 추출된 것(정상, 조치 불필요)과 같은 대상에 다른
    exclusion_type이 나온 것(LLM이 모순된 해석을 낸 신호, 사람 검수 필요)은
    성격이 다르므로 카운터가 어긋나면 안 된다.
    """

    def test_완전히_같은_값이_재추출되면_duplicate이지_conflict가_아니다(
        self, db_session
    ):
        # 시드의 (PERFORMANCE, CATEGORY, TAX)를 그대로 다시 추출한 상황.
        # LLM이 같은 조항을 다시 봐도 일관되게 분류한 정상 케이스다.
        loader = RuleLoader(db_session, card_id=CARD_A_ID)
        result = _result(
            [],
            content="세금은 실적 산정에서만 제외된다 (일관된 재추출)",
            exclusion_rules=[
                ExclusionRule(
                    exclusion_type=ExclusionType.PERFORMANCE,  # 시드와 동일
                    target_kind=TargetKind.CATEGORY,
                    target_value="TAX",
                )
            ],
        )

        report = loader.load(result)

        assert report.exclusion_rules == 0
        assert report.skipped_duplicate == 1
        assert report.skipped_conflict == 0
        assert report.conflicts == []

    def test_같은_대상에_다른_exclusion_type이_들어오면_conflict로_걸러지고_duplicate로_새지_않는다(
        self, db_session
    ):
        loader = RuleLoader(db_session, card_id=CARD_A_ID)
        result = _result(
            [],
            content="세금은 실적·할인 모두 제외된다 (오분류 재현)",
            exclusion_rules=[
                ExclusionRule(
                    exclusion_type=ExclusionType.BOTH,  # 시드는 PERFORMANCE — 충돌
                    target_kind=TargetKind.CATEGORY,
                    target_value="TAX",
                )
            ],
        )

        report = loader.load(result)

        assert report.exclusion_rules == 0
        assert report.skipped_duplicate == 0
        assert report.skipped_conflict == 1

        rows = db_session.execute(
            text(
                """
                SELECT exclusion_type FROM card_exclusion
                WHERE card_id = :card_id AND target_kind = 'CATEGORY' AND target_value = 'TAX'
                """
            ),
            {"card_id": CARD_A_ID},
        ).all()
        # 시드의 PERFORMANCE 행 하나만 있어야 한다. BOTH가 섞여 들어갔다면 충돌이 새어나간 것이다.
        assert len(rows) == 1
        assert rows[0][0] == "PERFORMANCE"

    def test_conflict_레코드에_기존_신규_값과_근거가_함께_담긴다(self, db_session):
        """사람이 어느 쪽이 맞는지 판단하려면 기존/신규 값과 근거 조항이 다 있어야 한다."""
        loader = RuleLoader(db_session, card_id=CARD_A_ID)
        new_content = "세금은 실적·할인 모두 제외된다 (오분류 재현, 근거 검증용)"
        result = _result(
            [],
            content=new_content,
            exclusion_rules=[
                ExclusionRule(
                    exclusion_type=ExclusionType.BOTH,
                    target_kind=TargetKind.CATEGORY,
                    target_value="TAX",
                )
            ],
        )

        report = loader.load(result)

        assert len(report.conflicts) == 1
        conflict = report.conflicts[0]
        assert conflict.card_id == CARD_A_ID
        assert conflict.target_kind == "CATEGORY"
        assert conflict.target_value == "TAX"
        assert conflict.existing_type == "PERFORMANCE"
        assert conflict.existing_verified is True  # 시드는 verified=true
        assert conflict.new_type == "BOTH"
        # 신규 근거는 이번에 적재한 조항 원문 그대로여야 한다.
        assert conflict.new_clause is not None
        assert conflict.new_clause["content"] == new_content
        # 시드의 (card_id=1, TAX) 행은 실제 제7조 원문에 연결돼 있다 — 이게
        # 바로 사람이 "어느 쪽이 맞는지" 판단할 기존 근거다.
        assert conflict.existing_clause is not None
        assert "세금" in conflict.existing_clause["content"]
        assert conflict.detected_at  # 빈 문자열이 아니어야 한다

    def test_같은_로더_인스턴스_안에서_적재한_제외규칙도_다음_load_호출에서_충돌_처리된다(
        self, db_session
    ):
        # 새 대상(MERCHANT/통합테스트가맹점)으로 먼저 적재한 뒤, 같은 로더로
        # 다른 exclusion_type을 넣으면 in-memory _seen_exclusions가 걸러야 한다.
        loader = RuleLoader(db_session, card_id=CARD_A_ID)
        first = _result(
            [],
            content="첫 적재",
            exclusion_rules=[
                ExclusionRule(
                    exclusion_type=ExclusionType.DISCOUNT,
                    target_kind=TargetKind.MERCHANT,
                    target_value="통합테스트가맹점",
                )
            ],
        )
        second = _result(
            [],
            content="같은 대상, 다른 exclusion_type 재시도",
            exclusion_rules=[
                ExclusionRule(
                    exclusion_type=ExclusionType.BOTH,
                    target_kind=TargetKind.MERCHANT,
                    target_value="통합테스트가맹점",
                )
            ],
        )

        report1 = loader.load(first)
        report2 = loader.load(second)

        assert report1.exclusion_rules == 1
        assert report1.skipped_duplicate == 0
        assert report1.skipped_conflict == 0
        assert report2.exclusion_rules == 0
        assert report2.skipped_duplicate == 0
        assert report2.skipped_conflict == 1
        # 방금 이 로더 인스턴스가 적재한 게 '기존' 값이 되므로 verified=False,
        # 근거는 first 조항 원문이어야 한다.
        conflict = report2.conflicts[0]
        assert conflict.existing_type == "DISCOUNT"
        assert conflict.existing_verified is False
        assert conflict.existing_clause is not None
        assert conflict.existing_clause["content"] == "첫 적재"


class TestExclusionScopeDbConstraint:
    """uq_exclusion_scope 가 RuleLoader 를 우회해도 실제로 막는지 검증한다.

    사전 검사가 아니라 raw INSERT로 직접 제약을 건드린다. db_session은
    테스트 종료 후 무조건 롤백하므로(conftest 참조) 여기서 만든 행은
    실제 시드를 오염시키지 않는다.
    """

    def test_같은_대상에_다른_exclusion_type을_직접_INSERT하면_DB_제약에_걸린다(
        self, db_session
    ):
        db_session.execute(
            text(
                """
                INSERT INTO card_exclusion
                    (card_id, exclusion_type, target_kind, target_value, verified)
                VALUES (:card_id, 'PERFORMANCE', 'CATEGORY', 'DB제약테스트', true)
                """
            ),
            {"card_id": CARD_A_ID},
        )

        with pytest.raises(IntegrityError):
            db_session.execute(
                text(
                    """
                    INSERT INTO card_exclusion
                        (card_id, exclusion_type, target_kind, target_value, verified)
                    VALUES (:card_id, 'BOTH', 'CATEGORY', 'DB제약테스트', true)
                    """
                ),
                {"card_id": CARD_A_ID},
            )


class TestRollbackDoesNotPollute:
    def test_db_session_트랜잭션은_테스트_종료_후_롤백되어_흔적이_남지_않는다(
        self, db_engine
    ):
        """conftest의 db_session이 실제로 격리되는지 별도 연결로 확인한다.

        RuleLoader 테스트가 실제로 시드를 오염시키지 않는다는 것을 이 테스트
        자체의 격리 증명으로 보여준다. db_session을 쓰지 않고 직접 트랜잭션을
        열고 닫아, 롤백 후 다른 연결에서 데이터가 보이지 않는지 확인한다.
        """
        connection = db_engine.connect()
        trans = connection.begin()
        session = sessionmaker(bind=connection)()
        try:
            loader = RuleLoader(session, card_id=CARD_A_ID)
            loader.load(
                _result(
                    [
                        BenefitRule(
                            perf_min=970_000,
                            perf_max=None,
                            category="FUEL",
                            discount_rate=Decimal("0.02"),
                        )
                    ],
                    content="롤백 격리 확인용 조항",
                )
            )
            # 트랜잭션 안에서는 방금 넣은 행이 보여야 한다.
            in_txn = session.execute(
                text(
                    "SELECT COUNT(*) FROM card_benefit_rule "
                    "WHERE card_id = :card_id AND perf_min = 970000"
                ),
                {"card_id": CARD_A_ID},
            ).scalar_one()
            assert in_txn == 1
        finally:
            session.close()
            trans.rollback()
            connection.close()

        with db_engine.connect() as verify_conn:
            after = verify_conn.execute(
                text(
                    "SELECT COUNT(*) FROM card_benefit_rule "
                    "WHERE card_id = :card_id AND perf_min = 970000"
                ),
                {"card_id": CARD_A_ID},
            ).scalar_one()
        # 커밋되지 않았으므로 별도 연결에서는 아예 보이지 않아야 한다.
        assert after == 0
