"""소비 카테고리 마스터 조회.

카테고리 코드를 코드에 하드코딩하지 않는다(CLAUDE.md "No hardcoded enums that
mirror DB data"). LLM 응답 스키마의 enum 은 이 목록으로 만든다.

## ALL 을 나눠 다루는 이유

`spend_category` 의 `ALL` 은 소비 카테고리가 아니라 **규칙 매칭용 와일드카드**다.
`card_benefit_rule.category` 가 `ALL` 이면 "카테고리 전용 규칙이 없을 때의
폴백" 을 뜻한다.

거래나 결제 요청의 카테고리로는 쓰이면 안 된다. 그러면 "카테고리 전용 규칙이
ALL 보다 우선한다" 는 우선순위 규칙이 의미를 잃는다 — 거래 자체가 ALL 이 되어
무엇이 전용이고 무엇이 폴백인지 구분할 수 없게 된다.

그래서 목록을 둘로 나눈다. 규칙을 다루는 쪽은 전체를, 결제·질의를 다루는 쪽은
`ALL` 을 뺀 목록을 쓴다.

## 캐시를 두지 않는 이유

마스터는 18행이라 조회가 사실상 무료이고, 런타임 경로의 LLM 호출(1.4초)에
비하면 무시할 수 있다. 반면 프로세스 캐시를 두면 운영 중 카테고리를 추가했을 때
재시작 전까지 새 코드가 계속 거부된다. 그건 CLAUDE.md 가 경계하는 "DB 소유 값
집합과 코드가 조용히 어긋나는" 상황을 하드코딩 대신 캐시로 재현하는 것이다.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

# 규칙 매칭용 와일드카드. 실제 결제 카테고리가 아니다.
WILDCARD_CATEGORY = "ALL"

_SQL = text("SELECT code FROM spend_category ORDER BY sort_no")
_SQL_WITH_LABEL = text("SELECT code, label FROM spend_category ORDER BY sort_no")


@dataclass(frozen=True, slots=True)
class SpendCategory:
    code: str
    label: str


def list_category_codes(session: Session) -> tuple[str, ...]:
    """마스터 전체. 와일드카드(ALL)를 포함한다 — 규칙을 다루는 쪽에서 쓴다."""
    return tuple(row[0] for row in session.execute(_SQL).all())


def list_purchase_category_codes(session: Session) -> tuple[str, ...]:
    """실제 결제에 붙을 수 있는 카테고리. 와일드카드를 뺀다.

    질의 해석과 결제 요청 검증은 이 목록을 써야 한다.
    """
    return tuple(c for c in list_category_codes(session) if c != WILDCARD_CATEGORY)


def list_categories(session: Session) -> tuple[SpendCategory, ...]:
    """마스터 전체를 라벨과 함께. 와일드카드(ALL)를 포함한다.

    규칙을 다루는 쪽에서 쓴다 — card_benefit_rule.category 는 ALL 을 가질 수
    있고, 보유 카드 화면은 그 규칙도 보여줘야 한다. 결제·질의용 목록은
    아래 list_purchase_categories 를 쓴다.
    """
    rows = session.execute(_SQL_WITH_LABEL).all()
    return tuple(SpendCategory(code=r[0], label=r[1]) for r in rows)


def list_purchase_categories(session: Session) -> tuple[SpendCategory, ...]:
    """화면 선택지용 목록. 코드와 함께 한글 라벨을 돌려준다.

    sort_no 순서를 그대로 유지한다 — 마스터가 이미 화면에 보여줄 순서로
    정렬돼 있으므로 프론트가 다시 정렬할 이유가 없다.

    라벨을 함께 내려보내는 이유는 코드와 같다. 화면이 "ONLINE → 온라인쇼핑"
    대응표를 들고 있으면 카테고리를 추가할 때 고쳐야 할 곳이 DB 와 프론트
    두 군데가 된다(CLAUDE.md "No hardcoded enums that mirror DB data").
    """
    rows = session.execute(_SQL_WITH_LABEL).all()
    return tuple(
        SpendCategory(code=r[0], label=r[1]) for r in rows if r[0] != WILDCARD_CATEGORY
    )
