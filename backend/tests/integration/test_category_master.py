"""spend_category 마스터와 VALID_CATEGORIES 정합성 테스트.

rag/models.py의 VALID_CATEGORIES는 LLM이 반환한 규칙을 적재 전에 검증하는
BenefitRule.validate()/ExclusionRule.validate()가 참조하는 하드코딩된 카테고리
목록이다. category_schema.get_category_codes_or_fallback()의 --dry-run 폴백도
이 값을 그대로 쓴다.

spend_category 마스터에 카테고리를 추가·변경했는데 VALID_CATEGORIES를 같이
고치지 않으면 두 가지가 조용히 어긋난다.

- DB(FK)는 허용하는 코드를 애플리케이션 검증이 거부하거나, 그 반대로
  애플리케이션 검증은 통과시키지만 실제로는 FK 위반이 되는 코드가 생긴다.
- dry-run의 category enum이 실적재 때 쓰는 DB 목록과 달라져,
  dry-run으로 확인한 추출 품질이 실제 상황을 대표하지 못하게 된다.

이 테스트는 그 어긋남을 잡아내는 안전망이다. 실패하면 spend_category와
VALID_CATEGORIES 중 하나만 고치고 나머지를 빠뜨렸다는 뜻이다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from src.rag.models import VALID_CATEGORIES

pytestmark = pytest.mark.integration


class TestCategoryMasterConsistency:
    def test_spend_category와_VALID_CATEGORIES가_정확히_일치한다(self, db_session):
        rows = db_session.execute(text("SELECT code FROM spend_category")).all()
        db_categories = {r[0] for r in rows}

        only_in_code = VALID_CATEGORIES - db_categories
        only_in_db = db_categories - VALID_CATEGORIES

        assert not only_in_code, (
            "VALID_CATEGORIES에는 있지만 spend_category에는 없는 코드: "
            f"{sorted(only_in_code)} — DB에 존재하지 않는 값을 유효하다고 "
            "검증하면 실제 적재 시 FK 위반으로 실패한다."
        )
        assert not only_in_db, (
            "spend_category에는 있지만 VALID_CATEGORIES에는 없는 코드: "
            f"{sorted(only_in_db)} — rag/models.py의 VALID_CATEGORIES를 갱신해야 한다. "
            "그렇지 않으면 이 카테고리에 대한 LLM 응답이 애플리케이션 검증 단계에서 "
            "부당하게 거부된다."
        )
