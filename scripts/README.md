# scripts

| 파일 | 담당 | 설명 |
|---|---|---|
| `generate_persona.py` | @mango606 | 페르소나별 6개월 거래 내역 생성 |
| `ingest_clauses.py` | @mango606 | 약관 PDF 파싱·규칙 추출·적재 |

## generate_persona.py

6개월치를 손으로 만드는 것은 불가능하므로 생성한다. 무작위가 아니라
실제 소비 패턴의 규칙성(요일 효과, 급여일 효과, 카테고리별 변동성,
일회성 대형 지출)을 반영한다. 균일 난수로 만들면 카테고리별 변동성이
사라져 예측 모듈의 분위수 밴드가 항상 좁게 나오고, 밴드가 제 역할을
하는지 확인할 방법이 없어진다.

주입한 규칙성을 예측 모듈이 전부 쓰는 것은 아니다. 응답 단위가 월말
잔고라 요일 효과는 한 달 안에서 상쇄되고, 월별 계절 효과는 같은 달을
두 번 이상 관측해야 추세와 분리되는데 6개월로는 불가능하다. 그래서
예측이 실제로 소비하는 것은 카테고리별 수준과 변동성, 그리고 일회성
대형 지출이다(판단 근거는 `docs/decisions/005-forecast-baseline.md`).

```bash
python scripts/generate_persona.py --months 6 --seed 42
psql $DATABASE_URL -f data/generated/transactions.sql
```

`--seed` 를 지정하면 매번 같은 결과가 나온다. 시연 데이터는 고정하는 편이
안전하므로 시드를 기록해 둔다.

## ingest_clauses.py

1단계 파이프라인이다. 조항을 하나씩 읽으면서 그 자리에서 규칙을 뽑고,
조항과 규칙을 함께 저장한다. 나중에 둘을 다시 매칭할 필요가 없다.

```bash
# 먼저 dry-run 으로 추출 품질을 확인한다. DB 연결이 필요 없다.
python scripts/ingest_clauses.py --card-id 1 --pdf data/clauses/a.pdf --dry-run --limit 5

# 확인 후 실제 적재
python scripts/ingest_clauses.py --card-id 1 --pdf data/clauses/a.pdf
```

### 재개

Rate limit 이나 네트워크 문제로 중단되면 처리 완료 목록이
`data/generated/ingest_progress.json` 에 남는다. 같은 명령을 다시 실행하면
처리하지 않은 조항부터 이어서 진행한다. 처음부터 다시 돌리면 비용과 시간이
이중으로 든다.

### 비용

LLM 응답은 `data/generated/llm_cache.json` 에 저장된다. 같은 조항을 다시
호출하지 않으므로 재실행 시 비용이 들지 않는다. 프롬프트를 수정했다면
`--no-cache` 를 쓴다.

키워드 필터가 규칙과 무관한 조항(분실 신고, 개인정보 처리 방침 등)을
먼저 걸러낸다. 전체를 LLM에 넣으면 비용이 몇 배가 되고 429도 나기 쉽다.

### 적재 후 검수

적재된 규칙은 모두 `verified=false` 다. 검수를 마쳐야 판정에 사용된다.

```sql
-- 검수 대기 목록. 근거 조항과 함께 확인한다.
SELECT r.id, r.category, r.discount_rate, r.perf_min, r.perf_max,
       c.doc_name, c.page_no, left(c.content, 100) AS clause
FROM card_benefit_rule r
JOIN clause_source c ON c.id = r.clause_id
WHERE r.verified = false AND r.card_id = 1
ORDER BY r.perf_min, r.category;

-- 확인 후 승인
UPDATE card_benefit_rule SET verified = true WHERE id = :id;
```

## 공통 주의

- 배치는 작업이 끝나면 DB 연결을 명시적으로 닫는다. 무료 티어 연결 한도가
  낮아 남겨두면 API 서버가 붙을 자리를 잠식한다. 두 스크립트 모두
  `dispose_engine()` 을 `finally` 에서 호출한다.
- LLM 호출에는 지수 백오프를 적용한다. 401 같은 영구 실패는 재시도하지
  않고 즉시 중단한다.
