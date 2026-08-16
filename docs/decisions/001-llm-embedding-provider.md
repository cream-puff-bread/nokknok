# 001. LLM 및 임베딩 제공자 선택

상태: **미확정 — Day 1에 결정 필요**
관련: `backend/requirements.txt`, `contracts/schema.sql` (`vector(1536)`)

## 문제

`.env.example` 에 `LLM_API_KEY` 와 `LLM_MODEL` 이 있고 `httpx` 와 `tenacity` 도 준비되어
있으나, 실제로 어떤 제공자를 쓸지 정하지 않았다. 이것이 정해지지 않으면 두 가지가 막힌다.

- 규칙 변환과 결과 설명에 쓸 SDK를 고를 수 없다
- `clause_source.embedding` 의 차원을 확정할 수 없다

## 두 가지를 따로 정해야 한다

**규칙 변환·설명 생성용 모델**과 **임베딩 모델**은 별개다.
Anthropic API에는 임베딩 엔드포인트가 없으므로, 규칙 변환에 Claude를 쓰더라도
임베딩은 다른 제공자를 함께 써야 한다.

## 임베딩 차원이 스키마에 박혀 있다

현재 스키마는 `vector(1536)` 이며, 이는 OpenAI `text-embedding-3-small` 기준이다.
다른 모델을 쓰면 차원이 달라지므로 스키마를 함께 고쳐야 한다.

| 모델 | 차원 |
|---|---|
| OpenAI text-embedding-3-small | 1536 |
| OpenAI text-embedding-3-large | 3072 |
| Voyage voyage-3 | 1024 |

**차원이 맞지 않으면 적재 시점에 오류가 난다.** Day 1에 임베딩 모델을 확정하고,
1536이 아니면 `schema.sql` 의 `vector(1536)` 과 `ivfflat` 인덱스를 함께 수정한다.

## 임베딩이 실제로 필요한 범위

런타임 경로에서는 벡터 검색을 쓰지 않는다. 근거 조항은 `ruleId` → `clause_id` 조인으로
특정한다. 임베딩은 규칙 변환 배치에서 "이 카드의 전월실적 관련 조항 찾기" 용도로만 쓴다.

시연 대상 카드가 3~5종이고 약관 PDF가 수십 페이지 수준이라면, 임베딩 없이
키워드 검색만으로도 충분할 수 있다. **임베딩 도입 자체를 재검토할 여지가 있다.**
도입하지 않기로 하면 `clause_source.embedding` 컬럼과 `ivfflat` 인덱스를 제거하고
의존성도 줄어든다.

## 결정 사항 (회의 후 기입)

- 규칙 변환·설명 생성 모델:
- 임베딩 사용 여부:
- 임베딩 모델 및 차원:
- 결정 근거:
