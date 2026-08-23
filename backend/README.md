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

구현 전에 아래 케이스를 먼저 작성한다. 계산 오류는 화면에 그럴듯한 숫자로
표시되어 발견이 늦다.

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
