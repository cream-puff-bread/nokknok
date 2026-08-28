"""결제 라우팅 최적화 — 후보 카드 조립.

qualification.py가 "규칙 하나를 어떻게 판정하는지"를 맡는다면, 여기는
"보유 카드 전체를 순회해 어느 카드로 결제할지"를 맡는다. 이 모듈도
DB·LLM을 모른다 — 호출부(src/api/)가 repository로 가져온 데이터를
인자로 넘긴다.

반환 타입에 explanation·clauses가 없다(backend/README.md "엔진은 LLM을
모른다"). LLM 설명과 근거 조항 조인은 src/api/가 이 결과 위에 조립한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.adapter.base import CardRef, Transaction
from src.common.exceptions import NoVerifiedRuleError
from src.engine.qualification import (
    classify_exclusions,
    compute_discount,
    minimum_qualifying_perf,
    performance_period,
    select_rule,
)
from src.repository.card import BenefitRule, Card, Exclusion

# 첫 구현 범위: 신규 구매는 항상 일시불로 가정한다. 할부·무이자 조합까지
# 탐색하려면 카드마다 결제방식별 실적/할인 결과를 각각 계산해야 하는데,
# 무이자 할부는 세 카드 모두 실적·할인 중 하나 이상에서 제외 대상이라
# (data/cards.seed.sql) 대부분의 경우 일시불이 유리하거나 동일하다.
# 할부가 유리한 예외 케이스(무이자 구간 없이 할부만 우대하는 카드)가
# 추가되면 이 가정을 재검토해야 한다.
ASSUMED_PAYMENT_TYPE = "LUMP"


@dataclass(frozen=True, slots=True)
class RouteCandidate:
    """contracts/api-spec.yaml의 RouteCandidate와 필드가 같아야 한다."""

    card_id: int
    card_name: str
    pay_date: date
    payment_type: str
    installment_months: int
    expected_discount: int
    perf_achieved: bool
    perf_current: int
    perf_required: int
    rule_id: int | None


@dataclass(frozen=True, slots=True)
class ComputeMeta:
    candidates_total: int
    candidates_pruned: int
    excluded_unverified_cards: int


@dataclass(frozen=True, slots=True)
class NewCardSuggestion:
    """contracts/api-spec.yaml의 newCardSuggestion과 필드가 같아야 한다."""

    card_name: str
    expected_gain: int
    is_affiliate: bool


@dataclass(frozen=True, slots=True)
class RouteResult:
    best: RouteCandidate
    alternatives: list[RouteCandidate]
    compute_meta: ComputeMeta
    new_card_suggestion: NewCardSuggestion | None = None


def _card_performance(
    transactions: list[Transaction],
    card_id: int,
    exclusions: list[Exclusion],
    period_start: date,
    period_end: date,
) -> int:
    """카드 하나의 실적 기간 내 실적 인정 금액 합계.

    같은 실적 기간이라도 카드마다 실적이 독립적이므로(persona_card 단위가
    아니라 card 단위 실적) 이 카드로 결제된 거래만 더한다. 무이자 할부처럼
    실적 제외 대상인 거래는 classify_exclusions로 걸러낸다.
    """
    total = 0
    for txn in transactions:
        if txn.card_id != card_id:
            continue
        if not (period_start <= txn.txn_date <= period_end):
            continue
        flags = classify_exclusions(exclusions, txn.category, txn.payment_type)
        if flags.performance_excluded:
            continue
        total += txn.amount
    return total


def suggest_new_card(
    owned_card_ids: set[int],
    cards_by_id: dict[int, Card],
    rules_by_card: dict[int, list[BenefitRule]],
    exclusions_by_card: dict[int, list[Exclusion]],
    amount: int,
    category: str,
) -> NewCardSuggestion | None:
    """보유하지 않은 카드 중 가장 유리한 카드를 제안한다.

    신규 카드는 이용자가 실제로 쓴 이력이 없으므로 perf_current=0으로
    가정한다 — 지어낸 미래 실적이 아니라 "이 카드를 지금 만들면 첫 구매부터
    받는 혜택"이라는 사실 그대로의 값이다. 0원짜리 혜택뿐이면 제안할
    이유가 없으므로 None을 반환한다.

    isAffiliate는 항상 False다. card 테이블에 제휴 여부 컬럼이 없고
    지금 카탈로그의 카드 3종은 전부 is_demo=true(가상 상품)라 실제
    제휴 카드가 없다 — 값을 지어내는 대신 사실대로 False로 둔다.
    제휴 카드가 생기면 schema.sql에 컬럼을 추가하는 계약 변경이 먼저다.
    """
    best: NewCardSuggestion | None = None
    best_gain = 0

    for card_id, card in cards_by_id.items():
        if card_id in owned_card_ids:
            continue
        rules = rules_by_card.get(card_id, [])
        if not any(r.verified for r in rules):
            continue

        exclusions = exclusions_by_card.get(card_id, [])
        rule = select_rule(rules, perf=0, category=category)
        flags = classify_exclusions(exclusions, category, ASSUMED_PAYMENT_TYPE)
        gain = compute_discount(rule, amount, flags.discount_excluded, card.monthly_cap)

        if gain > best_gain:
            best_gain = gain
            best = NewCardSuggestion(
                card_name=card.name, expected_gain=gain, is_affiliate=False
            )

    return best


def evaluate_route(
    owned_cards: list[CardRef],
    cards_by_id: dict[int, Card],
    rules_by_card: dict[int, list[BenefitRule]],
    exclusions_by_card: dict[int, list[Exclusion]],
    transactions: list[Transaction],
    amount: int,
    category: str,
    as_of: date,
) -> RouteResult:
    """보유 카드를 전부 평가해 최적 결제 카드를 고른다.

    검수 완료 규칙이 하나도 없는 카드는 후보에서 제외한다(카드 단위 —
    다른 카테고리 규칙이 검수돼 있어도 전부 미검수면 제외). 제외 후
    후보가 하나도 없으면 판정 자체가 불가능하므로 NoVerifiedRuleError를
    던진다 — API 계층이 이걸 409로 매핑한다(src/api/errors.py).

    cards_by_id/rules_by_card/exclusions_by_card는 카탈로그 전체를 담아
    넘겨도 된다 — 후보 평가는 owned_cards에 있는 card_id만 보고, 나머지는
    best.perf_achieved가 False일 때 suggest_new_card가 참조한다. 보유
    카드 데이터만 넘기면 newCardSuggestion은 항상 None이 된다.
    """
    candidates: list[RouteCandidate] = []
    excluded_unverified = 0

    for owned in owned_cards:
        card = cards_by_id.get(owned.card_id)
        if card is None:
            continue

        rules = rules_by_card.get(card.id, [])
        if not any(r.verified for r in rules):
            excluded_unverified += 1
            continue

        exclusions = exclusions_by_card.get(card.id, [])
        period_start, period_end = performance_period(
            card.perf_period_type,
            as_of,
            payment_day=owned.payment_day,
            billing_offset_days=card.billing_offset_days,
        )
        perf_current = _card_performance(
            transactions, card.id, exclusions, period_start, period_end
        )

        rule = select_rule(rules, perf_current, category)
        flags = classify_exclusions(exclusions, category, ASSUMED_PAYMENT_TYPE)
        expected_discount = compute_discount(
            rule, amount, flags.discount_excluded, card.monthly_cap
        )
        perf_required = minimum_qualifying_perf(rules, category) or 0

        candidates.append(
            RouteCandidate(
                card_id=card.id,
                card_name=owned.name,
                pay_date=as_of,
                payment_type=ASSUMED_PAYMENT_TYPE,
                installment_months=0,
                expected_discount=expected_discount,
                perf_achieved=perf_current >= perf_required,
                perf_current=perf_current,
                perf_required=perf_required,
                rule_id=rule.id if rule is not None else None,
            )
        )

    if not candidates:
        raise NoVerifiedRuleError(excluded_cards=excluded_unverified)

    # 예상 할인액 내림차순. 동률이면 이미 실적을 채운 카드를 우선한다 —
    # 할인액이 같다면 "지금 당장 받는" 카드가 "다음 달부터 받는" 카드보다
    # 화면에서 더 신뢰할 수 있는 추천이다.
    candidates.sort(key=lambda c: (-c.expected_discount, not c.perf_achieved))
    best = candidates[0]

    new_card_suggestion = None
    if not best.perf_achieved:
        # 보유 카드로 조건을 못 채울 때만 신규 카드를 제안한다
        # (contracts/api-spec.yaml: "보유 카드로 조건 충족 불가 시에만 존재").
        new_card_suggestion = suggest_new_card(
            owned_card_ids={c.card_id for c in owned_cards},
            cards_by_id=cards_by_id,
            rules_by_card=rules_by_card,
            exclusions_by_card=exclusions_by_card,
            amount=amount,
            category=category,
        )

    return RouteResult(
        best=best,
        alternatives=candidates[1:],
        compute_meta=ComputeMeta(
            candidates_total=len(owned_cards),
            candidates_pruned=0,
            excluded_unverified_cards=excluded_unverified,
        ),
        new_card_suggestion=new_card_suggestion,
    )
