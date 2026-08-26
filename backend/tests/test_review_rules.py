"""scripts/review_rules.py 단위 테스트.

DB 조회(fetch_pending)는 실제 세션이 필요해 통합 테스트 영역이다. 여기서는
파일 기반 충돌 이력(load_conflicts)과 순수 포맷 함수(format_conflict_entry,
build_markdown)만 검증한다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# review_rules.py는 backend/ 밖(scripts/)에 있다. test_ingest_clauses.py와
# 같은 이유로 scripts/를 sys.path에 넣는다.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

import review_rules as rr  # noqa: E402


def _record(**overrides) -> dict:
    fields = {
        "detected_at": "2026-08-24T00:00:00+00:00",
        "card_id": 1,
        "target_kind": "CATEGORY",
        "target_value": "TAX",
        "existing_type": "PERFORMANCE",
        "existing_verified": True,
        "existing_clause": None,
        "new_type": "BOTH",
        "new_clause": {"doc_name": "a.pdf", "page_no": 1, "content": "새 근거 원문"},
    }
    fields.update(overrides)
    return fields


class TestLoadConflicts:
    def test_파일이_없으면_빈_목록을_반환한다(self, tmp_path, monkeypatch):
        # review_rules는 이 파일이 없어도(아직 충돌이 없었거나 다른 환경) 그냥
        # 건너뛰어야 한다 — ingest_clauses.py가 먼저 실행돼야만 존재하는 파일이다.
        monkeypatch.setattr(rr, "CONFLICT_LOG_FILE", tmp_path / "없음.jsonl")
        assert rr.load_conflicts(None) == []

    def test_모든_줄을_읽는다(self, tmp_path, monkeypatch):
        path = tmp_path / "conflicts.jsonl"
        path.write_text(
            json.dumps(_record(card_id=1)) + "\n" + json.dumps(_record(card_id=2)) + "\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(rr, "CONFLICT_LOG_FILE", path)

        records = rr.load_conflicts(None)

        assert len(records) == 2
        assert {r["card_id"] for r in records} == {1, 2}

    def test_card_id로_필터링한다(self, tmp_path, monkeypatch):
        path = tmp_path / "conflicts.jsonl"
        path.write_text(
            json.dumps(_record(card_id=1)) + "\n" + json.dumps(_record(card_id=2)) + "\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(rr, "CONFLICT_LOG_FILE", path)

        records = rr.load_conflicts(2)

        assert len(records) == 1
        assert records[0]["card_id"] == 2

    def test_깨진_줄은_건너뛰고_나머지는_읽는다(self, tmp_path, monkeypatch):
        # 한 줄이 손상됐다고 나머지 충돌 이력까지 못 보게 되면 안 된다.
        path = tmp_path / "conflicts.jsonl"
        path.write_text(
            json.dumps(_record(card_id=1))
            + "\n{이건 유효한 JSON이 아니다\n"
            + json.dumps(_record(card_id=2))
            + "\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(rr, "CONFLICT_LOG_FILE", path)

        records = rr.load_conflicts(None)

        assert len(records) == 2
        assert {r["card_id"] for r in records} == {1, 2}


class TestFormatConflictEntry:
    def test_기존과_신규_값이_모두_보인다(self):
        text = rr.format_conflict_entry(_record())
        assert "PERFORMANCE" in text
        assert "BOTH" in text
        assert "TAX" in text

    def test_근거_조항_원문이_포함된다(self):
        text = rr.format_conflict_entry(_record())
        assert "새 근거 원문" in text

    def test_기존_근거가_없으면_안내_문구를_보여준다(self):
        text = rr.format_conflict_entry(_record(existing_clause=None))
        assert "근거 조항 없음" in text


class TestBuildMarkdownConflicts:
    def test_충돌_이력_섹션이_포함된다(self):
        markdown = rr.build_markdown([], [], card_id=1, conflicts=[_record()])
        assert "충돌 이력" in markdown
        assert "PERFORMANCE" in markdown
        assert "BOTH" in markdown

    def test_검수_대기_규칙이_없어도_충돌만_있으면_리포트가_비지_않는다(self):
        # 검수 대기(verified=false) 규칙이 하나도 없는 카드라도 충돌 이력은
        # 있을 수 있다("검수 대기 규칙이 없습니다"로 조용히 사라지면 안 된다).
        markdown = rr.build_markdown([], [], card_id=5, conflicts=[_record(card_id=5)])
        assert "검수 대기 규칙이 없습니다." not in markdown
        assert "card_id=5" in markdown

    def test_충돌도_없으면_기존과_동일하게_안내_문구를_보여준다(self):
        markdown = rr.build_markdown([], [], card_id=1, conflicts=[])
        assert "검수 대기 규칙이 없습니다." in markdown
