<div align="center">

# 넉넉

**지출이 확정된 금액을 제외한 가용잔고를 산출하고,<br>보유 카드 중 어떤 카드로 언제 결제할지까지 계산해 제시하는 AI 현금흐름 관리 서비스**

2026 금융 AI Challenge 출품작 · Team BankWay

</div>

---

## 문제

통장에 표시된 금액에는 다음 달 빠져나갈 구독료, 할부금, 대출 상환액이 이미 포함되어 있다. 이용자는 이를 사용 가능한 금액으로 인식해 소비하고, 월말에 이르러서야 자금 부족을 확인한다.

여기에 카드사마다 전월실적 산정 기간이 다르고 실적에서 제외되는 항목도 제각각이다. 결제일을 변경하면 실적 집계 기간이 달라져 혜택이 통째로 누락되기도 한다. **카드 3장만 보유해도 따져야 할 조건 조합이 수십 가지에 이른다.**

기존 서비스는 '어떤 카드를 새로 발급할지'를 추천하거나 '지난달 얼마를 지출했는지'를 정리하는 데 그친다. 이미 보유한 카드를 어떻게 조합해 언제 사용할지를 미리 판단해 주는 서비스는 없다.

## 해결

| 기능 | 설명 |
|---|---|
| **가용잔고 산출** | 구독료·할부 원리금·고정비 등 확정 지출을 제외한 실제 사용 가능 금액을 계산 |
| **6개월 시뮬레이션** | 자연어 질의를 받아 잔고 추이를 3개 시나리오로 제시하고 마이너스 전환 시점 표시 |
| **결제 라우팅 최적화** | 실적 조건·혜택 한도·제외 항목·청구 마감일을 종합해 최적 카드·시점·할부 조건 산출 |
| **근거 제시** | 판정의 근거가 된 약관 조항 원문을 함께 표시 |

## 기술적 선택

### 계산은 규칙 엔진이, 설명은 LLM이

금융 서비스에서 LLM이 금액을 잘못 계산하는 사고는 치명적이다. 계산 경로와 생성 경로를 아키텍처 수준에서 분리했다.

```
약관 PDF ──[배치] LLM 변환 → 사람 검수 → 규칙 테이블
                                            │
사용자 질의 ──[LLM] 파라미터 추출 ──→ 규칙 엔진 (금액 계산 전담)
                                            │
                                      결과 ──[LLM] 설명 생성
```

LLM 호출이 실패해도 계산 결과 자체는 표시된다. 설명만 빠지고 숫자는 나오는 것이 정상 동작이다.

### 검색을 런타임 응답 경로에 두지 않는다

검색 결과를 LLM이 그대로 읽고 답하게 하면 금액이나 기준일 같은 수치에서 오류가 발생한다. 실적 판정은 검수를 마친 규칙 테이블만 참조하고, 근거 조항은 적용된 규칙의 `clause_id` 조인으로 정확히 특정한다.

이 구조 덕분에 벡터 검색이 필요 없어졌다. 남은 용도는 배치가 조항과 규칙을 매칭하는 단계 하나뿐인데, 그마저 사람 검수 게이트가 있어 완벽한 의미 검색을 요구하지 않는다. 자세한 판단 근거는 [docs/decisions/001](./docs/decisions/001-no-vector-search.md) 참조.

### 통계적 시계열 예측

개인 한 명의 수개월치 데이터로 딥러닝 모델을 학습시키면 과적합이 발생하고 결과 설명도 어렵다. 카테고리별 이동평균과 중앙값에 요일·월중·월별 계절성을 반영하고, 분위수 기반 3개 시나리오 밴드를 산출한다.

### 데이터 소스 추상화

마이데이터 연동에는 본인신용정보관리업 허가가 필요하다. 표준 API 규격에 맞춰 인터페이스를 정의하고 구현체만 교체하는 구조로 설계했다.

| 구현체 | 용도 |
|---|---|
| Mock Provider | MVP 시연 |
| File Provider | 이용자가 카드사에서 내려받은 파일 |
| MyData Provider | 사업화 단계 |

## 기술 스택

**Backend** Python 3.11 · FastAPI · SQLAlchemy · Pydantic
**Data/AI** PostgreSQL · pg_trgm · LLM API
**Frontend** React · TypeScript · Tailwind CSS · Recharts
**Infra** Vercel · Render · Neon · GitHub Actions

FastAPI를 선택한 이유는 다음과 같다.

- 약관 파싱과 가상 데이터 생성의 라이브러리 생태계가 Python에 집중되어 있다
- Pydantic 모델이 `contracts/api-spec.yaml` 과 자동으로 대응되어, 별도 문서화 없이 OpenAPI 문서가 배포 환경에 노출된다
- 시계열 예측 모듈에 필요한 통계 연산을 표준 라이브러리 수준에서 처리할 수 있다

## 구조

```
nokknok/
├── contracts/          계약 파일 — 변경 시 전원 합의
│   ├── schema.sql
│   ├── api-spec.yaml
│   ├── types.ts
│   └── ui-system.md
├── backend/src/
│   ├── adapter/        데이터 소스 추상화
│   ├── rag/            약관 파이프라인
│   ├── engine/         최적화 엔진
│   ├── forecast/       시계열 예측
│   ├── repository/     DB 접근
│   └── api/            엔드포인트
├── frontend/src/
├── data/               시드 데이터
└── scripts/            데이터 생성·적재 배치
```

## 시작하기

### 사전 준비

Python 3.11 이상, Node.js 20 이상이 필요하다.

```bash
git clone https://github.com/cream-puff-bread/nokknok.git
cd nokknok
cp .env.example .env      # DATABASE_URL은 반드시 풀링(Pooled) 주소 사용
```

### 데이터베이스

```bash
psql $DATABASE_URL -f contracts/schema.sql
psql $DATABASE_URL -f data/cards.seed.sql
psql $DATABASE_URL -f data/personas.seed.sql
```

### 백엔드

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn src.main:app --reload --port 8000
```

API 문서는 `http://localhost:8000/docs` 에서 확인한다.

### 프론트엔드

```bash
cd frontend
npm install
npm run dev
```

## 시연 데이터에 대하여

`data/cards.seed.sql`에 정의된 카드는 **실제 시판 상품이 아닌 가상 상품**이다. 실제 카드사의 상품 조건을 임의로 기재하면 사실과 다를 수 있으므로, 국내 신용카드의 전형적인 규칙 구조만 차용해 구성했다.

세 카드는 서로 다른 규칙 구조를 갖도록 의도적으로 설계했다.

| 카드 | 구조 | 검증 목적 |
|---|---|---|
| NOKKNOK A | 계단형 (구간별 한도 차등) | 구간 탐색과 경계 판정 |
| NOKKNOK B | 단일 조건형 (청구 마감일 기준) | 결제일 변경 시 집계 기간 변동 |
| NOKKNOK C | 제외 항목 복잡형 | 실적 제외와 할인 제외의 구분 |

페르소나 역시 모두 가상 인물이며 실제 개인의 금융 데이터가 아니다.

## 팀

| 담당 | 영역 | GitHub |
|---|---|---|
| 손민주 | 데이터 생성 · 마이데이터 어댑터 · 약관 파이프라인 | [@mango606](https://github.com/mango606) |
| 박서희 | 최적화 엔진 · 데이터베이스 설계 | [@seohee-P](https://github.com/seohee-P) |
| 조하영 | API 서버 · 인프라 · 시계열 예측 | [@fanfanduck](https://github.com/fanfanduck) |

프론트엔드는 각자 담당한 백엔드 기능의 화면을 직접 구현한다.

- `@mango606` — 페르소나 선택 및 데이터 업로드, 규칙 검수 화면
- `@seohee-P` — 결제 라우팅 결과, 근거 약관 표시
- `@fanfanduck` — 가용잔고 대시보드, 시뮬레이션 입력, 잔고 추이 차트

## 협업 규칙

자세한 내용은 [CONTRIBUTING.md](./CONTRIBUTING.md) 참조.

- `contracts/` 변경은 전원 합의 후 진행
- AI로 코드 생성 시 `contracts/` 파일을 반드시 컨텍스트로 제공
- 외부 API 호출에는 예외 처리·타임아웃·지수 백오프 필수
- 커밋 메시지는 Conventional Commits 형식

## 미결 사항

코드 작성 전에 결정해야 하는 항목이다. 진행 상황은 [docs/decisions](./docs/decisions/)에서 추적한다.

| 항목 | 영향 |
|---|---|
| LLM 제공자 확정 | `requirements.txt` 의 SDK가 주석 처리된 상태 |
| 배치 파이프라인 1단계 / 2단계 | 1단계로 정해지면 `pg_trgm` 확장과 트라이그램 인덱스를 스키마에서 제거 |
