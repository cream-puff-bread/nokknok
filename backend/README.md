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
| `src/rag/` | mango606 | 약관 청킹·임베딩·규칙 변환 |
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
| 런타임 | `LLM_RUNTIME_TIMEOUT_BUDGET_MS` (총 예산) | `LLM_RUNTIME_MAX_RETRY` |

런타임은 총 예산 기준이므로 `tenacity` 의 `stop_after_delay` 를 사용한다.
`stop_after_attempt` 만 쓰면 응답 시간이 보장되지 않는다.

### 엔진은 LLM을 모른다

`src/engine/` 은 `src/rag/` 나 LLM 클라이언트를 import 하지 않는다.
엔진 반환 타입은 `RouteCandidate` 이며 `explanation` 과 `clauses` 를 갖지 않는다.
조립은 `src/api/` 가 담당한다.
