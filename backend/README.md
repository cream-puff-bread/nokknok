# backend

FastAPI 기반 API 서버.

## 실행

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn src.main:app --reload --port 8000
```

API 문서: http://localhost:8000/docs

## 테스트

```bash
pytest                                    # 330건
pytest -m "not integration"               # 227건. DB 없이 도는 것만
pytest tests/test_rag.py                  # 파일 하나
pytest -k "실적 or Extractor"              # 이름으로 (한글 테스트명이 섞여 있다)
```

통합 테스트는 실제 DB에 붙는다. `DATABASE_URL` 이 없으면 `tests/integration/`
전체가 자동으로 skip 되고 종료 코드는 0 이다 — **초록불이 곧 "통합까지 돌았다"
는 뜻은 아니다.** CI 는 시크릿이 있는데도 skip 이 생기면 실패시켜 그 착각을
막는다(`.github/workflows/ci.yml`).

conftest 가 트랜잭션을 열고 무조건 롤백하므로 시드 데이터는 건드리지 않는다.

## 엔드포인트

| 메서드 | 경로 | 내용 |
|---|---|---|
| GET | `/api/health` | 헬스체크. DB를 보지 않는다(keep-alive 가 커넥션 한도를 잠식하지 않게) |
| GET | `/api/personas` | 시연용 페르소나 목록 |
| GET | `/api/balance` | 가용잔고, 확정 지출, 이번 달 하루 단위 잔고 전망 |
| GET | `/api/cards` | 보유 카드 현황 (실적 누적액·적용 혜택·제외 항목) |
| GET | `/api/categories` | `spend_category` 마스터. 화면이 코드를 지어내지 않게 |
| GET | `/api/spending` | 카테고리별 소비 집계. `month` 생략 시 거래가 있는 마지막 달 |
| POST | `/api/simulate` | 6개월 현금흐름. `query`(자연어) 또는 `purchase`(구조화) |
| POST | `/api/route` | 결제 라우팅 최적화 |

응답 형식은 `contracts/api-spec.yaml` 이 원본이다.

## 구조

| 경로 | 담당 | 내용 |
|---|---|---|
| `src/adapter/` | mango606 | 마이데이터 규격 데이터 소스 추상화 |
| `src/rag/` | mango606 | 약관 파싱·조항 적재·규칙 변환 (1단계 파이프라인) |
| `src/engine/` | seohee-P | 결제 조합 최적화, 실적 판정 |
| `src/repository/` | seohee-P | DB 접근 |
| `src/api/` | fanfanduck | 엔드포인트, 응답 조립 |
| `src/forecast/` | fanfanduck | 변동 지출 시계열 예측 |
| `src/common/` | 공통 | 예외, 로깅, LLM 클라이언트, 설정 |

## 주의

### Pydantic 모델은 contracts/api-spec.yaml 을 따른다

FastAPI가 자동 생성하는 OpenAPI 문서와 `contracts/api-spec.yaml` 이 어긋나면
프론트가 잘못된 형식을 기준으로 작업하게 된다. 응답 모델을 바꿀 때는
계약 파일도 같은 커밋에서 갱신한다.

### 계산의 기준일은 DEMO_TODAY 를 따른다

`date.today()` 를 직접 부르지 않는다. 계산에 쓰는 오늘은
`src/common/clock.py` 의 `reference_date()` 하나로 받는다.

시연 데이터는 특정 시점의 스냅샷이다 — `persona.account_balance` 는 계산값이
아니라 시드에 손으로 적은 상수이고 거래도 그 시점까지만 있다. 그런데 예측이
실제 달력을 따라가면 둘이 어긋난다. 페르소나 2 / 200만원 일시불의 보통
시나리오 첫 달 잔고가 이렇게 움직였다.

| 기준일 | 잔고 |
|---|---|
| 2026-09-05 | −8,621 |
| 2026-09-06 | **+44,728** (위기가 사라진다) |
| 2026-09-10 | **−2,624,877** (급여일을 넘기며 290만원이 통째로 빠진다) |

9/10 의 절벽은 `_income_schedule` 이 급여일을 지났으면 이번 달 급여를 0 으로
두는데, 시드 잔액이 급여 받기 전 금액이라 없는 돈을 빼기 때문이다.

심사는 URL 만 받아 아무 날에나 열어 보는 방식이라, 같은 화면이 여는 날에 따라
"안전" 도 되고 "260만원 부족" 도 되면 안 된다. 그래서 기준일을 시드가 만들어진
시점(**2026-08-20**, 세 페르소나의 마지막 거래일)에 고정한다.

- **배포 환경에도 반드시 넣는다.** 빠뜨리면 실제 오늘로 돌아가 화면이 날마다
  달라지는데, 예외가 나지 않아 알아채기 어렵다. 기동 로그에 `기준일=...(고정)`
  또는 `(실제 오늘)` 로 찍히므로 그것으로 확인한다.
- 벽시계 시각이 필요한 곳(`/api/health` 의 응답 시각, RAG 의 수집 시각)에는
  쓰지 않는다. 그건 계산의 기준이 아니라 사건이 실제로 일어난 시각이다.
- `src/forecast/` 는 설정을 모른다. 기준일을 인자로 받는 지금 형태를 유지하고,
  호출부(`src/api/`)가 `reference_date()` 를 넘긴다 — 예측을 DB 도 설정도 없이
  테스트할 수 있는 이유가 이것이다.
- 실제 데이터를 붙이는 날 `DEMO_TODAY` 를 지우면 원래대로 돌아간다.
- `forecast_cashflow()` 의 `today` 는 **필수 인자**다. 예전에는
  `today or date.today()` 로 흘려보냈는데, 그러면 안 넘긴 호출부가 조용히
  실제 오늘로 빠진다 — 이 설정이 막으려는 그 실패다. 빠뜨리면 예외로 드러난다.
- `reference_date()` 는 **전역 `get_settings()` 를 읽는다.**
  `create_app(Settings(DEMO_TODAY=...))` 로 주입해도 기준일은 안 바뀐다.
  이 함수가 어댑터의 `FixedExpense` 처럼 요청 문맥이 없는 자리에서도 불리기
  때문이다. 테스트에서 다른 날짜가 필요하면 계산 함수에 `today` 를 직접
  넘기거나 `src.common.clock.get_settings` 를 monkeypatch 한다.

### 커넥션 풀 상한

`DB_POOL_MAX` 를 5 내외로 유지한다. 무료 티어 동시 연결 한도가 낮고,
배치 스크립트가 API 서버와 동시에 DB에 붙는다.

```python
create_engine(settings.database_url, pool_size=settings.db_pool_max, max_overflow=0)
```

`max_overflow=0` 을 명시해야 상한이 실제로 지켜진다.

### LLM 호출은 경로별로 설정을 분리한다

배치용과 런타임용 설정을 공유하지 않는다. `src/common/` 에 두 개의
클라이언트를 두거나, 호출 시 프로파일을 인자로 받는다.

| 경로 | 타임아웃 | 재시도 |
|---|---|---|
| 배치 | `LLM_BATCH_TIMEOUT_MS` | `LLM_BATCH_MAX_RETRY` |
| 런타임 | `LLM_RUNTIME_TIMEOUT_BUDGET_MS` (총 예산) | 없음 (예산이 곧 중단 기준) |

런타임은 총 예산 기준이므로 `tenacity` 의 `stop_after_delay` 를 사용한다.
`stop_after_attempt` 만 쓰면 응답 시간이 보장되지 않는다.

### 구조화된 출력은 응답 스키마로 강제한다

LLM에게 "JSON으로 답해줘"라고 프롬프트에 적는 것만으로는 부족하다.
Gemini의 응답 스키마 지정 기능을 써서 출력 형식을 강제한다.

값 집합이 고정된 필드는 반드시 enum으로 지정한다.

| 필드 | 값 집합 |
|---|---|
| `category` | `spend_category` 테이블의 `code` 전체 |
| `paymentType` | `LUMP` / `INSTALLMENT` / `INTEREST_FREE` |

**enum 값을 코드에 하드코딩하지 않는다.** `spend_category` 를 조회해 스키마를
동적으로 만든다. 코드에 목록을 다시 적으면 카테고리를 추가할 때 두 곳을 고쳐야 하고,
한쪽을 빠뜨리면 모델이 DB에 없는 값을 반환한다.

응답 스키마를 지정해도 형식 위반이 아예 불가능해지는 것은 아니므로, 파싱 후
`spend_category` 존재 여부를 한 번 더 확인하고 실패 시 422로 응답한다.

### 무료 티어 요청 한도 대응

Gemini 무료 티어는 분당·일일 요청 한도가 있다. 배치에서 약관을 연속 처리하면
한도에 걸리기 쉽다.

- 재시도만으로 부족하다. **배치는 요청 간 간격을 두어 분당 한도 아래로 유지**한다
- 429 응답의 `Retry-After` 헤더가 있으면 그 값을 우선한다
- 변환 완료된 약관은 파일로 캐싱해 재실행 시 건너뛴다
- 한도와 모델 구성은 자주 바뀌므로 공식 문서에서 현재 값을 확인한다

### 엔진은 LLM을 모른다

`src/engine/` 은 `src/rag/` 나 LLM 클라이언트를 import 하지 않는다.
엔진 반환 타입은 `RouteCandidate` 이며 `explanation` 과 `clauses` 를 갖지 않는다.
조립은 `src/api/` 가 담당한다.

### 규칙 적용 우선순위

같은 실적 구간에 카테고리 전용 규칙과 `ALL` 와일드카드 규칙이 함께 존재할 수 있다.
**적용 규칙은 항상 하나만 선택하며 합산하지 않는다.**

| 순위 | 조건 | 적용 |
|---|---|---|
| 1 | 결제 카테고리와 정확히 일치하는 규칙 존재 | 그 규칙 |
| 2 | 일치 규칙 없고 `ALL` 규칙 존재 | `ALL` 규칙 |
| 3 | 둘 다 없음 | 할인 없음 |

`category_cap` 도 선택된 규칙의 값만 쓴다. 두 규칙의 한도를 더하지 않는다.

조회 예시:

```sql
SELECT id, discount_rate, category_cap
FROM card_benefit_rule
WHERE card_id = :card_id
  AND perf_min <= :perf
  AND (perf_max IS NULL OR :perf < perf_max)
  AND category IN (:category, 'ALL')
ORDER BY CASE WHEN category = :category THEN 0 ELSE 1 END
LIMIT 1;
```

`ORDER BY` 로 전용 규칙을 먼저 오게 하고 `LIMIT 1` 로 하나만 취한다.
`WHERE category IN (...)` 만 쓰고 두 행을 모두 받아 더하면 존재하지 않는
할인율이 계산된다.

### 엔진 필수 단위 테스트

엔진을 고칠 때 아래 케이스가 계속 도는지 확인한다. 계산 오류는 화면에 그럴듯한
숫자로 표시되어 발견이 늦다 — 이 표는 구현 전에 먼저 적어 둔 것이고, 지금은
전부 테스트로 들어가 있다.

| 케이스 | 기대값 |
|---|---|
| 카드 C, ONLINE 결제, 실적 충족 | 10% (ALL 1%를 더한 11%가 아님) |
| 카드 C, TRANSPORT 결제, 실적 충족 | ALL 규칙 매치되나 DISCOUNT 제외로 할인 0원, 실적에는 반영 |
| 카드 C, TAX 결제 | 실적에 미반영 (PERFORMANCE 제외) |
| 카드 A, 실적 499,999원 / 500,000원 | 구간 경계에서 한도가 바뀌는지 |
| 카드 A, 무이자 할부 결제 | 실적·할인 모두 제외 (BOTH) |
| 카드 B, 결제일 변경 | 청구 마감일 기준이므로 실적 집계 기간이 달라지는지 |
| 카테고리 한도 초과 | `category_cap` 에서 잘리는지 |
| 월 통합 한도 초과 | `monthly_cap` 에서 잘리는지 |
| 모든 규칙의 `clause_id` | `NULL` 이 없는지. 하나라도 비면 근거 표시가 빈 화면이 된다 |
