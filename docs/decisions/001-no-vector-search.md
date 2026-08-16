# 001. 벡터 검색을 도입하지 않는다

상태: **확정**
관련: `contracts/schema.sql`, `backend/requirements.txt`

## 배경

초기 설계에서는 약관 PDF를 청킹·임베딩해 `pgvector`에 색인하고, 검색 증강 생성으로
규칙을 추출하는 구조를 잡았다. `clause_source.embedding` 은 `vector(1536)` 이었고
`ivfflat` 인덱스를 두었다.

이후 두 차례 설계 변경을 거치며 벡터 검색의 필요 범위가 계속 줄었다.

1. **런타임 경로에서 제거** — 검색 결과를 LLM이 그대로 읽고 답하게 하면 금액이나
   기준일 같은 수치에서 오류가 발생한다. 판정은 검수를 마친 규칙 테이블만 참조하도록
   바꿨다.
2. **근거 조항 조회에서 제거** — `card_benefit_rule.clause_id` 가 이미 FK로 존재하고,
   엔진은 자신이 적용한 규칙을 안다. `ruleId` 를 결과에 실으면 조인 한 번으로 근거를
   정확히 특정할 수 있다. 검색으로 찾으면 실제 적용된 규칙과 어긋날 여지가 생긴다.

## 결정

**벡터 검색을 도입하지 않는다.** `pgvector` 확장, `embedding` 컬럼, `ivfflat` 인덱스를
모두 제거한다.

## 근거

### 남은 용도가 하나이고, 그마저 완벽한 검색을 요구하지 않는다

위 두 변경 이후 남은 용도는 "배치가 규칙을 추출할 때 근거 조항을 찾아 연결"하는 것뿐이다.
그런데 이 단계에는 `verified` 검수 게이트가 있다. 자동 매칭이 100% 정확할 필요가 없고
후보 몇 개만 추려주면 사람이 고른다. 의미 검색을 도입할 만큼 요구 정확도가 높지 않다.

### 파이프라인 구조에 따라 검색 자체가 불필요하다

조항을 순차 처리하며 각 조항에서 규칙을 뽑는 1단계 구조라면, 추출 시점에 이미
`clause_source.id` 를 손에 쥐고 있으므로 그대로 함께 저장하면 된다.
검색은 "이미 뽑힌 규칙과 조항 뭉치를 나중에 매칭"하는 2단계 구조에서만 필요하다.

**@mango606은 파이프라인을 1단계로 설계하는 것을 우선 검토한다.** 가능하면 조항 검색
논의 자체가 사라진다.

### 제거하면 미결 사항이 함께 해소된다

임베딩 모델을 정하지 못해 `requirements.txt` 에 SDK가 주석 처리된 상태였다.
차원이 스키마에 `vector(1536)` 으로 고정되어 있어 모델을 바꾸면 마이그레이션이
필요했다. 벡터를 빼면 임베딩 모델 선택 자체가 불필요해진다.

`ivfflat` 인덱스도 카드 3~5종, 약관 수십 페이지 규모에는 과설계였다.
이 규모에서는 인덱스 없이 전체 스캔이 더 빠르다.

또한 Anthropic API에는 임베딩 엔드포인트가 없다. 규칙 변환에 Claude를 쓰기로 하면
임베딩만을 위해 별도 제공자를 하나 더 붙여야 했는데, 그 부담도 사라진다.

## 대안: 검색이 필요하면 pg_trgm

2단계 파이프라인이 필요하다고 판단되면 트라이그램 유사도를 쓴다.

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX idx_clause_content_trgm ON clause_source USING gin (content gin_trgm_ops);

SELECT id, doc_name, page_no, similarity(content, :query) AS score
FROM clause_source
WHERE card_id = :card_id
ORDER BY score DESC
LIMIT 5;
```

Postgres 기본 `tsvector` 전문 검색은 한국어에서 어미 변화(제외됩니다 / 제외함 / 제외한다)
때문에 형태소 분석기 없이는 매칭이 잘 되지 않는다. `pg_trgm` 은 문자 단위 n-gram이라
언어와 무관하게 부분 문자열 유사도를 잡아내고, 외부 API 의존성이 전혀 없다.

## 결과

- 외부 임베딩 API 의존성 제거
- 임베딩 모델 선택 및 차원 고정 문제 해소
- 스키마에서 `vector` 확장, `embedding` 컬럼, `ivfflat` 인덱스 제거
- `requirements.txt` 에서 `pgvector` 제거

## 후속 결정

`docs/decisions/002` 에서 두 가지가 확정되었다.

- LLM 제공자: Gemini
- 배치 파이프라인: 1단계 구조. 이에 따라 조항 검색 자체가 불필요해져
  `pg_trgm` 확장과 트라이그램 인덱스도 제거했다. `clause_source` 는
  검색 대상이 아닌 순수 원문 보관 테이블이 되었다.
