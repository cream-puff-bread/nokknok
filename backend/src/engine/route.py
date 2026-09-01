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
from datetime import date, timedelta

from src.adapter.base import CardRef, Transaction
from src.common.exceptions import NoVerifiedRuleError
from src.engine.qualification import (
    classify_exclusions,
    compute_discount,
    minimum_qualifying_perf,
    next_close_date,
    performance_period,
    select_rule,
)
from src.repository.card import BenefitRule, Card, Exclusion

# 탐색하는 결제방식 두 가지. 할부 개월 수(3개월/6개월 등)는 따로 조합에
# 넣지 않는다 — compute_discount가 할인율에 개월 수를 쓰지 않으므로
# 계산 결과가 완전히 같고, "일시불 vs 무이자할부" 구분만 결과를 가른다
# (2026-08-29 하영님 스코프 확정).
LUMP = "LUMP"
INTEREST_FREE = "INTEREST_FREE"

# 무이자 할부 후보에 표시할 개월 수. 위 이유로 discount 계산에는 영향이
# 없는 표시값이라 아무 값이나 대표로 고정해도 된다 — 3/6개월 중 더 흔한
# 쪽을 쓴다.
INTEREST_FREE_INSTALLMENT_MONTHS = 6


@dataclass(frozen=True, slots=True)
class RouteCandidate:
    """contracts/api-spec.yaml의 RouteCandidate와 필드가 같아야 한다."""

    card_id: int
    card_name: str
    # 실제 카드 상품이 아닌 시연용 가상 상품임을 화면에 표시하기 위한 값이다
    # (schema.sql card.is_demo, contracts/ui-system.md "시연용 가상 카드에는
    # 반드시 뱃지를 표시한다"). 계산에는 쓰이지 않는다 — 화면이 지어낼 수 없는
    # 값이라 계산 결과와 같은 경로로 실어 보낸다.
    is_demo: bool
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
    is_demo: bool
    expected_gain: int
    is_affiliate: bool


@dataclass(frozen=True, slots=True)
class RouteResult:
    best: RouteCandidate
    alternatives: list[RouteCandidate]
    compute_meta: ComputeMeta
    new_card_suggestion: NewCardSuggestion | None = None


def card_performance(
    transactions: list[Transaction],
    card_id: int,
    exclusions: list[Exclusion],
    period_start: date,
    period_end: date,
) -> int:
    """카드 하나의 실적 기간 내 실적 인정 금액 합계.

    보유 카드 화면(GET /api/cards)도 같은 숫자를 보여줘야 해서 공개한다.
    API 계층이 따로 합산하면 라우팅 결과의 실적과 카드 화면의 실적이 다르게
    나올 수 있는데, 같은 값을 두 곳에서 다르게 말하는 것이 이 서비스가 가장
    하지 말아야 할 일이다(CLAUDE.md: 금액 계산은 엔진이 전담한다).

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
        # 신규 카드 제안은 "오늘 일시불로 첫 구매"라는 가장 단순한 기준으로
        # 기대 이득을 보여준다 — 아직 만들지도 않은 카드의 결제방식·날짜
        # 조합까지 탐색하는 건 과한 추정이다.
        flags = classify_exclusions(exclusions, category, LUMP)
        gain = compute_discount(rule, amount, flags.discount_excluded, card.monthly_cap)

        if gain > best_gain:
            best_gain = gain
            best = NewCardSuggestion(
                card_name=card.name,
                is_demo=card.is_demo,
                expected_gain=gain,
                is_affiliate=False,
            )

    return best


def _pay_date_candidates(
    card: Card, owned: CardRef, as_of: date, due_date: date | None
) -> list[date]:
    """오늘 결제 vs 마감일 다음날 결제, 두 후보 날짜를 만든다.

    due_date가 없으면 "미룬다"는 선택지 자체가 정의되지 않으므로 오늘
    하나만 반환한다. 다음 마감일이 due_date보다 뒤라면(카드 B 시드처럼
    28일 단위 주기에서 짧은 기한 안에 마감이 안 오는 경우) 그 후보는
    아예 만들지 않는다 — "마감을 놓쳐서 못 미루는" 상태를 억지로 앞당기지
    않는다.
    """
    candidates = [as_of]
    if due_date is None:
        return candidates
    close = next_close_date(
        card.perf_period_type,
        as_of,
        payment_day=owned.payment_day,
        billing_offset_days=card.billing_offset_days,
    )
    delayed = close + timedelta(days=1)
    if delayed <= due_date:
        candidates.append(delayed)
    return candidates


def _evaluate_card(
    card: Card,
    owned: CardRef,
    rules: list[BenefitRule],
    exclusions: list[Exclusion],
    transactions: list[Transaction],
    amount: int,
    category: str,
    as_of: date,
    due_date: date | None,
) -> tuple[list[RouteCandidate], int, int]:
    """카드 하나에 대해 (결제일 × 결제방식) 조합을 전부 평가한다.

    반환값의 후보 리스트는 이 카드가 만들어낸 조합 전부다 — 최종적으로
    하나만 골라 RouteResponse에 싣는 건 호출부(evaluate_route) 몫이다.
    두 번째·세 번째 값은 각각 시도한 조합 수, 가지치기로 건너뛴 조합 수다.
    """
    payment_types = [LUMP]
    interest_free_flags = classify_exclusions(exclusions, category, INTEREST_FREE)
    # 무이자 할부가 실적·할인 모두 제외(BOTH)면 어떤 날짜와 짝지어도 결과가
    # 전부 0원으로 같다 — 계산 없이도 결론을 알 수 있으므로 아예 평가하지
    # 않는다(카드 A/B가 이 경우다). 카드 C처럼 실적만 제외(PERFORMANCE)면
    # 할인이 살아있으므로 반드시 평가해야 한다 — "무이자=혜택 0원"으로
    # 단순화하면 안 되는 이유가 이것이다(2026-08-29 하영님 확인).
    both_excluded = interest_free_flags.performance_excluded and interest_free_flags.discount_excluded
    if not both_excluded:
        payment_types.append(INTEREST_FREE)

    pay_dates = _pay_date_candidates(card, owned, as_of, due_date)
    pruned = len(pay_dates) if both_excluded else 0
    attempted = len(pay_dates) * len(payment_types)

    rule_by_date: dict[date, BenefitRule | None] = {}
    perf_by_date: dict[date, int] = {}
    perf_required = minimum_qualifying_perf(rules, category) or 0

    for pay_date in pay_dates:
        period_start, period_end = performance_period(
            card.perf_period_type,
            pay_date,
            payment_day=owned.payment_day,
            billing_offset_days=card.billing_offset_days,
        )
        # period_end가 미래(오늘 이후)일 수 있다 — pay_date를 마감일
        # 다음날로 미룬 후보는 "아직 지나지 않은 기간"을 참조하기 때문이다.
        # 그 구간을 그대로 합산하면 아직 일어나지 않은 지출을 0원으로
        # 취급해 실적이 체계적으로 과소 집계된다(2026-08-29 하영님 지적 —
        # 미룬 후보만 항상 손해로 나오는 구조적 편향). 오늘까지 실제로
        # 지난 부분만 더해 "이미 확정된 실적"만 센다.
        counted_end = min(period_end, as_of)
        perf_current = card_performance(
            transactions, card.id, exclusions, period_start, counted_end
        )
        perf_by_date[pay_date] = perf_current
        rule_by_date[pay_date] = select_rule(rules, perf_current, category)

    candidates: list[RouteCandidate] = []
    for pay_date in pay_dates:
        perf_current = perf_by_date[pay_date]
        rule = rule_by_date[pay_date]
        for payment_type in payment_types:
            flags = classify_exclusions(exclusions, category, payment_type)
            expected_discount = compute_discount(
                rule, amount, flags.discount_excluded, card.monthly_cap
            )
            candidates.append(
                RouteCandidate(
                    card_id=card.id,
                    card_name=owned.name,
                    is_demo=card.is_demo,
                    pay_date=pay_date,
                    payment_type=payment_type,
                    installment_months=(
                        INTEREST_FREE_INSTALLMENT_MONTHS if payment_type == INTEREST_FREE else 0
                    ),
                    expected_discount=expected_discount,
                    # 오늘까지 실적이 이미 기준을 넘었으면 확정이다 — 앞으로
                    # 더 써도 줄어들지 않으므로 안전하게 true로 둔다. 아직
                    # 못 넘었으면 false로 두되 "틀렸다"고 확정하지 않는다.
                    # perfRequired - perfCurrent를 프론트가 그대로 보여주면
                    # "마감까지 N원 더 쓰면 충족"이 된다(새 계약 필드 불필요,
                    # 2026-08-29 하영님 제안 ②).
                    perf_achieved=perf_current >= perf_required,
                    perf_current=perf_current,
                    perf_required=perf_required,
                    rule_id=rule.id if rule is not None else None,
                )
            )

    return candidates, attempted, pruned


def evaluate_route(
    owned_cards: list[CardRef],
    cards_by_id: dict[int, Card],
    rules_by_card: dict[int, list[BenefitRule]],
    exclusions_by_card: dict[int, list[Exclusion]],
    transactions: list[Transaction],
    amount: int,
    category: str,
    as_of: date,
    due_date: date | None = None,
) -> RouteResult:
    """보유 카드를 전부 평가해 최적 결제 카드를 고른다.

    카드마다 (오늘/마감일 다음날 결제) × (일시불/무이자할부) 조합을 만들어
    평가하고, 그중 그 카드에 가장 유리한 조합 하나만 후보로 남긴다 —
    RouteResponse는 카드당 한 행이라는 기존 형태를 그대로 유지한다.

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
    candidates_total = 0
    candidates_pruned = 0

    for owned in owned_cards:
        card = cards_by_id.get(owned.card_id)
        if card is None:
            continue

        rules = rules_by_card.get(card.id, [])
        if not any(r.verified for r in rules):
            excluded_unverified += 1
            continue

        exclusions = exclusions_by_card.get(card.id, [])
        card_candidates, attempted, pruned = _evaluate_card(
            card, owned, rules, exclusions, transactions, amount, category, as_of, due_date
        )
        candidates_total += attempted
        candidates_pruned += pruned

        # 이 카드가 만든 조합 중 가장 유리한 하나만 최종 후보로 남긴다.
        # 동률이면 실적을 이미 채운 쪽, 그다음 더 이른 결제일을 우선한다 —
        # "지금 당장 받는" 결과가 "마감까지 기다려야 하는" 결과보다 화면에서
        # 더 신뢰할 수 있는 추천이다.
        card_candidates.sort(key=lambda c: (-c.expected_discount, not c.perf_achieved, c.pay_date))
        candidates.append(card_candidates[0])

    if not candidates:
        raise NoVerifiedRuleError(excluded_cards=excluded_unverified)

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
            candidates_total=candidates_total,
            candidates_pruned=candidates_pruned,
            excluded_unverified_cards=excluded_unverified,
        ),
        new_card_suggestion=new_card_suggestion,
    )
