-- 넉넉(nokknok) 데이터베이스 스키마
-- 변경 시 전원 합의 필수. 변경 후 이 파일과 마이그레이션을 함께 커밋한다.

-- pg_trgm: 조항 검색이 필요한 경우에만 사용하는 트라이그램 유사도 확장.
-- 벡터 확장(pgvector)은 사용하지 않는다. 근거는 docs/decisions/001 참조.
-- 파이프라인 구조가 1단계로 확정되면 이 확장도 제거한다. docs/decisions/002 참조.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ─────────────────────────────────────────────
-- 소비 카테고리 마스터
--
-- category / target_value 를 자유 텍스트로 두면 'DINNING' 같은 오탈자가
-- 들어가도 DB가 받아주고, 엔진은 매칭 실패를 조용히 넘긴다.
-- 할인이 0원으로 계산되어도 오류가 아니므로 발견이 매우 늦다.
-- 마스터 테이블로 분리해 적재 시점에 걸러낸다.
-- ─────────────────────────────────────────────
CREATE TABLE spend_category (
    code    VARCHAR(40) PRIMARY KEY,
    label   VARCHAR(60) NOT NULL,
    sort_no SMALLINT    NOT NULL DEFAULT 0
);

INSERT INTO spend_category (code, label, sort_no) VALUES
('ALL',       '전체',        0),
('DINING',    '외식',       10),
('CAFE',      '카페',       20),
('DELIVERY',  '배달',       30),
('GROCERY',   '장보기',     40),
('ONLINE',    '온라인쇼핑', 50),
('TRANSPORT', '교통',       60),
('FUEL',      '주유',       70),
('MEDICAL',   '의료',       80),
('EDUCATION', '교육',       90),
('CULTURE',   '문화',      100),
('TELECOM',   '통신',      110),
('UTILITY',   '공과금',    120),
('TAX',       '세금',      130),
('INSURANCE', '보험',      140),
('GIFT_CARD', '상품권',    150),
('SUBSCRIPTION', '구독',   160),
('ETC',       '기타',      999);

-- ─────────────────────────────────────────────
-- 카드 상품 마스터
-- ─────────────────────────────────────────────
CREATE TABLE card (
    id                  SERIAL PRIMARY KEY,
    issuer              VARCHAR(50)  NOT NULL,        -- 카드사명
    name                VARCHAR(100) NOT NULL,        -- 카드명
    perf_period_type    VARCHAR(20)  NOT NULL,        -- MONTH_START | BILLING_CYCLE
    billing_close_day   SMALLINT,                     -- 청구 마감일. NULL이면 말일
    monthly_cap         INTEGER,                      -- 월 통합 할인 한도(원). NULL이면 무제한
    source_url          TEXT,                         -- 상품 안내장 출처
    is_demo             BOOLEAN NOT NULL DEFAULT false, -- 시연용 가상 상품 여부
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT chk_billing_close_day CHECK (billing_close_day IS NULL OR billing_close_day BETWEEN 1 AND 28),
    CONSTRAINT chk_perf_period       CHECK (perf_period_type IN ('MONTH_START', 'BILLING_CYCLE'))
);

COMMENT ON COLUMN card.is_demo IS '실제 카드 상품이 아닌 시연용 가상 상품임을 표시. 화면에도 명시해야 한다.';

-- ─────────────────────────────────────────────
-- 실적 구간별 혜택 규칙
--
-- 계단형 구조를 컬럼이 아닌 행으로 표현한다.
-- 컬럼으로 고정하면 구간 수가 다른 카드를 담을 수 없다.
--
-- ⚠️ 규칙 적용 우선순위 (엔진 구현 시 반드시 준수)
--
--   같은 실적 구간에 카테고리 전용 규칙과 ALL 와일드카드 규칙이
--   동시에 존재할 수 있다. 이때 적용 규칙은 하나만 선택한다.
--
--     1) 결제 카테고리와 정확히 일치하는 규칙이 있으면 그것을 적용
--     2) 없으면 ALL 규칙을 폴백으로 적용
--     3) 둘 다 없으면 할인 없음
--
--   두 규칙을 합산하지 않는다. 예를 들어 카드 C는 ONLINE 10%와 ALL 1%를
--   함께 갖지만, ONLINE 결제의 할인율은 11%가 아니라 10%다.
--   합산하면 실제로 존재하지 않는 할인을 화면에 표시하게 된다.
--
--   category_cap 역시 선택된 규칙의 값만 적용한다.
-- ─────────────────────────────────────────────
CREATE TABLE card_benefit_rule (
    id                  SERIAL PRIMARY KEY,
    card_id             INTEGER NOT NULL REFERENCES card(id) ON DELETE CASCADE,
    perf_min            INTEGER NOT NULL,             -- 실적 하한(원), 포함
    perf_max            INTEGER,                      -- 실적 상한(원), 미포함. NULL이면 무제한
    category            VARCHAR(40) NOT NULL REFERENCES spend_category(code),
    discount_rate       NUMERIC(5,4) NOT NULL,        -- 0.0500 = 5%
    category_cap        INTEGER,                      -- 해당 카테고리 월 한도(원)
    clause_id           INTEGER,                      -- 근거 조항
    verified            BOOLEAN NOT NULL DEFAULT false, -- 사람 검수 완료 여부
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_perf_range CHECK (perf_max IS NULL OR perf_max > perf_min),
    CONSTRAINT chk_rate       CHECK (discount_rate >= 0 AND discount_rate <= 1),
    -- 같은 카드·구간·카테고리에 규칙이 둘 이상 있으면 어느 것을 적용할지
    -- 결정할 수 없다. 적재 시점에 차단한다.
    CONSTRAINT uq_rule_scope  UNIQUE (card_id, perf_min, perf_max, category)
);

CREATE INDEX idx_rule_card_perf  ON card_benefit_rule (card_id, perf_min, perf_max);
CREATE INDEX idx_rule_unverified ON card_benefit_rule (card_id) WHERE verified = false;

-- ─────────────────────────────────────────────
-- 실적 제외 / 할인 제외 항목
-- 실적 제외와 할인 제외는 다르다. 무이자 할부는 실적에 잡히지 않지만
-- 할인은 적용되는 카드가 있으므로 반드시 구분한다.
-- ─────────────────────────────────────────────
CREATE TABLE card_exclusion (
    id                  SERIAL PRIMARY KEY,
    card_id             INTEGER NOT NULL REFERENCES card(id) ON DELETE CASCADE,
    exclusion_type      VARCHAR(20) NOT NULL,
    target_kind         VARCHAR(20) NOT NULL,
    target_value        VARCHAR(60) NOT NULL,
    clause_id           INTEGER,
    verified            BOOLEAN NOT NULL DEFAULT false,
    CONSTRAINT chk_exclusion_type CHECK (exclusion_type IN ('PERFORMANCE', 'DISCOUNT', 'BOTH')),
    CONSTRAINT chk_target_kind    CHECK (target_kind IN ('CATEGORY', 'MERCHANT', 'PAYMENT_TYPE')),
    -- target_value 는 target_kind 에 따라 참조 대상이 달라져 FK를 걸 수 없다.
    -- PAYMENT_TYPE 만 값 집합이 고정이므로 여기서 검증하고,
    -- CATEGORY 는 아래 무결성 검증 쿼리로 확인한다.
    CONSTRAINT chk_payment_type_target CHECK (
        target_kind <> 'PAYMENT_TYPE'
        OR target_value IN ('LUMP', 'INSTALLMENT', 'INTEREST_FREE')
    )
);

CREATE INDEX idx_exclusion_card ON card_exclusion (card_id, exclusion_type);

-- ─────────────────────────────────────────────
-- 근거 약관 조항
--
-- 판정 근거를 화면에 제시하기 위한 원문 보관 테이블이다.
-- 런타임에서는 card_benefit_rule.clause_id 조인으로 정확히 특정하므로
-- 어떤 형태의 검색도 필요하지 않다.
--
-- 임베딩 컬럼을 두지 않는 이유는 docs/decisions/001 참조.
-- 요약하면, 검색이 필요한 경우가 배치의 조항-규칙 매칭 하나뿐인데
-- 그 단계에는 verified 검수 게이트가 있어 완벽한 의미 검색이 필요하지 않다.
-- ─────────────────────────────────────────────
CREATE TABLE clause_source (
    id                  SERIAL PRIMARY KEY,
    card_id             INTEGER NOT NULL REFERENCES card(id) ON DELETE CASCADE,
    doc_name            VARCHAR(200) NOT NULL,
    page_no             SMALLINT,
    content             TEXT NOT NULL,                -- 조항 원문
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_clause_card ON clause_source (card_id);

-- ⚠️ 결정 대기 — docs/decisions/002
--
-- 배치 파이프라인이 조항 추출과 규칙 변환을 분리해 2단계로 동작하는 경우에만
-- 아래 트라이그램 인덱스가 필요하다. 한국어는 어미 변화 때문에 tsvector 기반
-- 전문 검색이 형태소 분석기 없이는 잘 맞지 않는 반면, pg_trgm은 문자 단위
-- n-gram이라 언어와 무관하게 부분 문자열 유사도를 잡아낸다.
--
-- 파이프라인이 1단계(조항을 읽으면서 그 자리에서 규칙을 추출하고
-- clause_source.id를 함께 저장)로 확정되면 이 인덱스와 상단의
-- pg_trgm 확장을 함께 제거한다.
--
-- 현재는 결정 전이므로 생성해 둔다. 수백 row 규모에서 GIN 인덱스 하나의
-- 비용은 무시할 수준이고, 나중에 필요해졌을 때 마이그레이션이 생기는 편이
-- 더 번거롭다. 결정 후 정리를 잊지 말 것.
CREATE INDEX idx_clause_content_trgm ON clause_source USING gin (content gin_trgm_ops);

-- 조회 예시
-- SELECT id, doc_name, page_no, similarity(content, :query) AS score
-- FROM clause_source
-- WHERE card_id = :card_id
-- ORDER BY score DESC
-- LIMIT 5;

ALTER TABLE card_benefit_rule
    ADD CONSTRAINT fk_rule_clause FOREIGN KEY (clause_id) REFERENCES clause_source(id);
ALTER TABLE card_exclusion
    ADD CONSTRAINT fk_exclusion_clause FOREIGN KEY (clause_id) REFERENCES clause_source(id);

-- ─────────────────────────────────────────────
-- 페르소나 (시연용 가상 이용자)
-- ─────────────────────────────────────────────
CREATE TABLE persona (
    id                  SERIAL PRIMARY KEY,
    code                VARCHAR(30) UNIQUE NOT NULL,  -- SUBSCRIPTION_HEAVY | INSTALLMENT_HEAVY | STABLE
    display_name        VARCHAR(60) NOT NULL,
    description         TEXT,
    account_balance     INTEGER NOT NULL,             -- 현재 계좌 잔액(원)
    monthly_income      INTEGER NOT NULL,
    income_day          SMALLINT NOT NULL,            -- 급여일
    CONSTRAINT chk_income_day CHECK (income_day BETWEEN 1 AND 28)
);

CREATE TABLE persona_card (
    id                  SERIAL PRIMARY KEY,
    persona_id          INTEGER NOT NULL REFERENCES persona(id) ON DELETE CASCADE,
    card_id             INTEGER NOT NULL REFERENCES card(id),
    payment_day         SMALLINT NOT NULL,            -- 결제일
    UNIQUE (persona_id, card_id)
);

-- ─────────────────────────────────────────────
-- 거래 내역
-- ─────────────────────────────────────────────
CREATE TABLE transaction (
    id                  BIGSERIAL PRIMARY KEY,
    persona_id          INTEGER NOT NULL REFERENCES persona(id) ON DELETE CASCADE,
    card_id             INTEGER REFERENCES card(id),  -- NULL이면 계좌 이체
    txn_date            DATE NOT NULL,
    merchant            VARCHAR(120) NOT NULL,
    amount              INTEGER NOT NULL,             -- 원. 지출은 양수
    category            VARCHAR(40) NOT NULL REFERENCES spend_category(code),
    payment_type        VARCHAR(20) NOT NULL,
    installment_months  SMALLINT NOT NULL DEFAULT 0,
    is_recurring        BOOLEAN NOT NULL DEFAULT false,
    CONSTRAINT chk_txn_payment_type CHECK (payment_type IN ('LUMP', 'INSTALLMENT', 'INTEREST_FREE')),
    CONSTRAINT chk_installment      CHECK (
        (payment_type = 'LUMP' AND installment_months = 0)
        OR (payment_type <> 'LUMP' AND installment_months > 0)
    )
);

CREATE INDEX idx_txn_persona_date ON transaction (persona_id, txn_date DESC);
CREATE INDEX idx_txn_card_date    ON transaction (card_id, txn_date);
CREATE INDEX idx_txn_recurring    ON transaction (persona_id) WHERE is_recurring = true;

-- ─────────────────────────────────────────────
-- 확정 지출 (구독 / 할부 / 고정비)
-- ─────────────────────────────────────────────
CREATE TABLE fixed_expense (
    id                  SERIAL PRIMARY KEY,
    persona_id          INTEGER NOT NULL REFERENCES persona(id) ON DELETE CASCADE,
    expense_type        VARCHAR(20) NOT NULL,         -- SUBSCRIPTION | INSTALLMENT | LOAN | INSURANCE
    label               VARCHAR(120) NOT NULL,
    amount              INTEGER NOT NULL,             -- 월 납입액(원)
    charge_day          SMALLINT NOT NULL,
    remaining_months    SMALLINT,                     -- NULL이면 무기한(구독 등)
    last_used_date      DATE,                         -- 미사용 구독 판별용
    card_id             INTEGER REFERENCES card(id),
    CONSTRAINT chk_charge_day   CHECK (charge_day BETWEEN 1 AND 28),
    CONSTRAINT chk_expense_type CHECK (expense_type IN ('SUBSCRIPTION', 'INSTALLMENT', 'LOAN', 'INSURANCE'))
);

CREATE INDEX idx_fixed_persona ON fixed_expense (persona_id, expense_type);

-- ─────────────────────────────────────────────
-- 무결성 검증 쿼리
--
-- card_exclusion.target_value 는 target_kind 에 따라 참조 대상이 달라
-- FK를 걸 수 없다. 규칙 적재 후 아래 쿼리로 확인한다.
-- 결과가 한 건이라도 나오면 오탈자가 들어간 것이다.
-- ─────────────────────────────────────────────
-- SELECT e.id, e.card_id, e.target_value
-- FROM card_exclusion e
-- WHERE e.target_kind = 'CATEGORY'
--   AND NOT EXISTS (SELECT 1 FROM spend_category c WHERE c.code = e.target_value);

-- 대응하는 혜택 규칙이 없어 실질적으로 아무것도 걸러내지 못하는 제외 항목 탐지.
-- 의도한 케이스일 수도 있으므로 오류가 아닌 점검용이다.
-- SELECT e.id, e.card_id, e.target_value
-- FROM card_exclusion e
-- WHERE e.exclusion_type IN ('DISCOUNT', 'BOTH')
--   AND e.target_kind = 'CATEGORY'
--   AND NOT EXISTS (
--     SELECT 1 FROM card_benefit_rule r
--     WHERE r.card_id = e.card_id
--       AND r.category IN (e.target_value, 'ALL')
--   );
