# 003. card_exclusion 중복 적재 방지

상태: **미확정** — `contracts/schema.sql` 변경이라 전원 합의 필요
관련: `contracts/schema.sql`, `backend/src/rag/loader.py`, `data/cards.seed.sql`

## 문제

`card_benefit_rule`은 `uq_rule_scope UNIQUE (card_id, perf_min, perf_max, category)`
제약이 있어, 같은 구간·카테고리 규칙이 두 번 들어가면 DB가 막는다. `card_exclusion`에는
대응하는 제약이 없다. `RuleLoader`가 적재 전에 기존 값을 읽어 애플리케이션 레벨에서
걸러내긴 하지만(`_load_existing_exclusions`), 이건 DB 제약이 아니라 사전 검사일 뿐이라
우회될 수 있다 — 그리고 실제로 우회됐다.

## 발견 경위

1. `data/clauses.seed.sql`의 card_id=1 조항 원문으로 테스트용 PDF(`data/clauses/nokknok-a.pdf`)를
   만들고 `scripts/ingest_clauses.py --card-id 1 --pdf data/clauses/nokknok-a.pdf --dry-run --limit 5`로
   먼저 추출 품질을 확인했다.
2. 이후 같은 PDF로 실적재를 돌렸다. 혜택 규칙(제5조) 9건은 시드 값과 정확히 일치했지만,
   제외 규칙(제7조)에서 `card_exclusion`에 새 행이 하나 더 들어갔다.
3. `scripts/README.md`의 검수 쿼리로 card_id=1의 `verified=false`를 조회하다가
   `card_benefit_rule`은 0건인데 `card_exclusion`에 1건(id=12)이 남아 있는 걸 발견했다.

## 실제 사례 (id=12)

`data/cards.seed.sql`에는 이미 다음이 `verified=true`로 존재한다.

```
id=2  card_id=1  PERFORMANCE / CATEGORY / TAX   (근거: 제7조)
```

제7조 원문: "다음 각 호의 이용금액은 전월 이용실적 산정과 할인 적용에서 모두 제외됩니다.
… 2. 국세, 지방세 등 각종 세금 납부금액(단, 세금은 실적 산정에서만 제외되며 할인 대상
업종에 해당하지 않습니다)." — 괄호 안 단서 때문에 세금은 `PERFORMANCE`(실적에서만 제외)가
맞는 해석이다.

그런데 같은 조항을 다시 LLM에 넣었을 때, 이번엔 괄호 속 단서를 놓치고 문단 첫머리
"모두 제외됩니다"만 따라가 `BOTH`로 분류했다. 그 결과가 그대로 적재됐다.

```
id=12 card_id=1  BOTH / CATEGORY / TAX   (verified=false, 근거: 같은 제7조)
```

`RuleLoader._seen_exclusions`의 사전 검사 키는 `(exclusion_type, target_kind, target_value)`
세 개 전부다. id=2와 id=12는 `target_kind`·`target_value`(`CATEGORY`/`TAX`)는 같지만
`exclusion_type`이 다르므로(`PERFORMANCE` ≠ `BOTH`) 이 사전 검사를 그대로 통과했다.
DB에도 이를 막을 제약이 없어 두 행이 나란히 남았다.

id=12는 조항 원문과 대조해 `PERFORMANCE`가 맞는 해석임을 확인했고, 이미 id=2가 그 값으로
존재하므로 고치는 대신 삭제했다(2026-08-20). 삭제 후 card_id=1의 `verified=false`는
`card_benefit_rule`·`card_exclusion` 모두 0건이다.

## 제안

```sql
ALTER TABLE card_exclusion
    ADD CONSTRAINT uq_exclusion_scope
    UNIQUE (card_id, exclusion_type, target_kind, target_value);
```

`card_benefit_rule.uq_rule_scope`와 대칭을 이루는 구조이고, `RuleLoader`의 사전 검사가
우회되는 경로(동시 실행, 사전 검사 없는 다른 적재 경로, 수기 INSERT 등)에서 완전
동일한 행이 두 번 들어가는 것은 이 제약으로 막을 수 있다.

## 이 제안으로는 못 막는 것 — 논의 필요

id=12 사례를 이 제약에 그대로 대입하면, **막지 못했을 것이다.** id=2와 id=12는
`exclusion_type`이 다르므로(`PERFORMANCE` vs `BOTH`) 네 컬럼(`card_id`,
`exclusion_type`, `target_kind`, `target_value`) 전체가 일치하는 조건을 만족하지 않는다.

이번에 실제로 발생한 문제는 "완전히 같은 행이 두 번 들어간 것"이 아니라 "같은
`(target_kind, target_value)`에 대해 서로 다른 `exclusion_type`이 공존한 것"이다. 이
둘은 의미상 양립할 수 없다 — 세금이 `PERFORMANCE` 제외이면서 동시에 `BOTH` 제외일 수는
없다. 이 케이스까지 막으려면 `exclusion_type`을 뺀

```sql
UNIQUE (card_id, target_kind, target_value)
```

쪽이 더 정확할 수 있다. 다만 이렇게 좁히면 "같은 `target_value`가 카드 안에서 서로 다른
`exclusion_type`을 정말로 가져야 하는" 합법적 케이스가 있는지부터 확인해야 한다. 현재
시드 데이터에는 그런 케이스가 보이지 않지만, 다른 카드 유형에서 나올 수 있는지 확신이
서지 않아 판단을 전원 논의로 남긴다.

두 후보 중 무엇을 택하든, `RuleLoader._seen_exclusions`의 사전 검사 키도 같은 기준으로
맞춰야 한다 — 지금처럼 키가 어긋나 있으면 DB 제약을 추가해도 애플리케이션 레벨에서는
같은 실패가 재현되고, `IntegrityError`가 배치 중간에 던져져 그 조항 전체가 유실된다
(`loader.py` 상단 주석 참조: "DB에 맡기면 IntegrityError 로 트랜잭션이 깨져 나머지
조항이 날아간다").

## 결정

미확정. 다음 두 가지를 함께 정해야 한다.

1. 제약 범위 — 네 컬럼 전체(`uq_exclusion_scope` 원안) vs `exclusion_type`을 뺀 좁은 범위.
2. `RuleLoader`의 사전 검사 키를 결정된 제약과 동일하게 맞출지.

결정 후 `contracts/schema.sql`과 `backend/src/rag/loader.py`를 같은 커밋에서 갱신한다.
