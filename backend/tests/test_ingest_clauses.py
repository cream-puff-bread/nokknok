"""scripts/ingest_clauses.py 단위 테스트.

배치 스크립트지만 순수 함수(clause_key, _print_result)는 DB나 LLM 없이도
검증할 수 있다.
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

# ingest_clauses.py는 backend/ 밖(scripts/)에 있다. 이 스크립트가 스스로
# backend/를 sys.path에 넣는 것과 대칭으로, 여기서는 scripts/를 넣는다.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

import ingest_clauses as ic  # noqa: E402

from src.rag.loader import ExclusionConflict  # noqa: E402
from src.rag.models import BenefitRule, Clause, ExtractionResult  # noqa: E402


def _conflict(**overrides) -> ExclusionConflict:
    fields = {
        "detected_at": "2026-08-24T00:00:00+00:00",
        "card_id": 1,
        "target_kind": "CATEGORY",
        "target_value": "TAX",
        "existing_type": "PERFORMANCE",
        "existing_verified": True,
        "existing_clause": None,
        "new_type": "BOTH",
        "new_clause": {"doc_name": "a.pdf", "page_no": 1, "content": "새 근거"},
    }
    fields.update(overrides)
    return ExclusionConflict(**fields)


class TestClauseKey:
    def test_카테고리_소스가_다르면_같은_조항도_다른_키를_받는다(self):
        """실제 사고 재현: dry-run(폴백 VALID_CATEGORIES)과 실적재(DB
        spend_category)는 서로 다른 category enum으로 LLM을 호출할 수
        있는데, 예전 clause_key는 이를 무시해 같은 조항이면 무조건 같은
        캐시 키를 냈다. 카테고리 소스가 다르면 실제로 다른 질의이므로
        키도 달라야 한다.
        """
        clause = Clause(doc_name="a.pdf", page_no=1, content="조항 내용입니다" * 3)
        key_fallback = ic.clause_key(1, clause, ("ALL", "DINING", "ETC"))
        key_db = ic.clause_key(1, clause, ("ALL", "DINING", "ETC", "NEW_CATEGORY"))
        assert key_fallback != key_db

    def test_같은_카테고리_목록이면_같은_키를_낸다(self):
        """재개(resume) 기능이 동작하려면 같은 조건에서 키가 안정적이어야 한다."""
        clause = Clause(doc_name="a.pdf", page_no=1, content="조항 내용입니다" * 3)
        key1 = ic.clause_key(1, clause, ("ALL", "DINING"))
        key2 = ic.clause_key(1, clause, ("ALL", "DINING"))
        assert key1 == key2

    def test_카드나_조항_내용이_다르면_키도_다르다(self):
        categories = ("ALL", "DINING")
        c1 = Clause(doc_name="a.pdf", page_no=1, content="조항 A" * 5)
        c2 = Clause(doc_name="a.pdf", page_no=1, content="조항 B" * 5)
        assert ic.clause_key(1, c1, categories) != ic.clause_key(1, c2, categories)
        assert ic.clause_key(1, c1, categories) != ic.clause_key(2, c1, categories)


class TestPrintResult:
    def test_category_cap이_0이면_한도없음으로_표시하지_않는다(self, capsys):
        """review_rules.py에서 고친 것과 같은 버그: category_cap == 0을
        falsy로 판정하면 "한도없음"으로 잘못 표시된다.
        """
        result = ExtractionResult(
            clause=Clause(doc_name="a.pdf", page_no=1, content="테스트 조항 내용입니다"),
            benefit_rules=[
                BenefitRule(
                    perf_min=300_000,
                    perf_max=None,
                    category="DINING",
                    discount_rate=Decimal("0.05"),
                    category_cap=0,
                )
            ],
        )
        ic._print_result(result)
        captured = capsys.readouterr()
        assert "한도없음" not in captured.out
        assert "0원" in captured.out

    def test_perf_max가_0이면_무제한으로_표시하지_않는다(self, capsys):
        """같은 truthy 판정 버그가 perf_max에도 있었다. 실제 데이터에서
        나올 값은 아니지만(perf_max=0은 chk_perf_range 위반), 표시
        로직 자체의 방어를 검증하는 단위 테스트다.
        """
        result = ExtractionResult(
            clause=Clause(doc_name="a.pdf", page_no=1, content="테스트 조항 내용입니다"),
            benefit_rules=[
                BenefitRule(
                    perf_min=-1,
                    perf_max=0,
                    category="DINING",
                    discount_rate=Decimal("0.05"),
                )
            ],
        )
        ic._print_result(result)
        captured = capsys.readouterr()
        assert "무제한" not in captured.out


class TestAppendConflicts:
    """review_rules.py가 읽을 파일을 만드는 쪽이므로 형식이 깨지면 안 된다."""

    def test_충돌이_없으면_파일을_만들지_않는다(self, tmp_path):
        path = tmp_path / "conflicts.jsonl"
        ic.append_conflicts(path, [])
        assert not path.exists()

    def test_충돌_한_줄이_유효한_JSON으로_append된다(self, tmp_path):
        path = tmp_path / "conflicts.jsonl"
        ic.append_conflicts(path, [_conflict()])

        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["card_id"] == 1
        assert record["existing_type"] == "PERFORMANCE"
        assert record["new_type"] == "BOTH"
        assert record["new_clause"]["content"] == "새 근거"

    def test_여러_번_호출하면_이어_append된다(self, tmp_path):
        # 배치가 조항마다 append_conflicts를 부르므로, 실행이 끝날 때까지
        # 이전 줄을 덮어쓰면 안 된다.
        path = tmp_path / "conflicts.jsonl"
        ic.append_conflicts(path, [_conflict(target_value="TAX")])
        ic.append_conflicts(path, [_conflict(target_value="GIFT_CARD")])

        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["target_value"] == "TAX"
        assert json.loads(lines[1])["target_value"] == "GIFT_CARD"
