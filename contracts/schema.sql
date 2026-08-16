-- 넉넉(nokknok) 데이터베이스 스키마
-- 변경 시 전원 합의 필수. 변경 후 이 파일과 마이그레이션을 함께 커밋한다.

CREATE EXTENSION IF NOT EXISTS vector;

-- ─────────────────────────────────────────────
-- 카드 상품 마스터
-- ─────────────────────────────────────────────
CREATE TABLE card (
    id                  SERIAL PRIMARY KEY,
    issuer              VARCHAR(50)  NOT NULL,        -- 카드사명
    name                VARCHAR(100) NOT NULL,        -- 카드명
    perf_period_type    VARCHAR(20)  NOT NULL,        -- MONTH_START | BILLING_CYCLE
    billing_close_day   SMALLINT,                     -- 청구 마감일 (1~28, NULL이면 말일)
    monthly_cap         INTEGER,                      -- 월 통합 할인 한도(원). NULL이면 무제한
    source_url          TEXT,                         -- 상품 안내장 출처
    is_demo             BOOLEAN NOT NULL DEFAULT false, -- 시연용 가상 상품 여부
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now()
);

COMMENT ON COLUMN card.is_demo IS '실제 카드 상품이 아닌 시연용 가상 상품임을 표시. 화면에도 명시해야 한다.';

-- ─────────────────────────────────────────────
-- 실적 구간별 혜택 규칙
-- 계단형 구조를 컬럼이 아닌 행으로 표현한다.
-- 컬럼으로 고정하면 구간 수가 다른 카드를 담을 수 없다.
-- ─────────────────────────────────────────────
CREATE TABLE card_benefit_rule (
    id                  SERIAL PRIMARY KEY,
    card_id             INTEGER NOT NULL REFERENCES card(id) ON DELETE CASCADE,
    perf_min            INTEGER NOT NULL,             -- 실적 하한(원), 포함
    perf_max            INTEGER,                      -- 실적 상한(원), 미포함. NULL이면 무제한
    category            VARCHAR(40) NOT NULL,         -- ALL | DINING | TRANSPORT | ONLINE | ...
    discount_rate       NUMERIC(5,4) NOT NULL,        -- 0.0500 = 5%
    category_cap        INTEGER,                      -- 해당 카테고리 월 한도(원)
    clause_id           INTEGER,                      -- 근거 조항
    verified            BOOLEAN NOT NULL DEFAULT false, -- 사람 검수 완료 여부
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_perf_range CHECK (perf_max IS NULL OR perf_max > perf_min),
    CONSTRAINT chk_rate       CHECK (discount_rate >= 0 AND discount_rate <= 1)
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
    exclusion_type      VARCHAR(20) NOT NULL,         -- PERFORMANCE | DISCOUNT | BOTH
    target_kind         VARCHAR(20) NOT NULL,         -- CATEGORY | MERCHANT | PAYMENT_TYPE
    target_value        VARCHAR(60) NOT NULL,         -- TAX | UTILITY | GIFT_CARD | INTEREST_FREE ...
    clause_id           INTEGER,
    verified            BOOLEAN NOT NULL DEFAULT false
);

CREATE INDEX idx_exclusion_card ON card_exclusion (card_id, exclusion_type);

-- ─────────────────────────────────────────────
-- 근거 약관 조항 (RAG)
-- ─────────────────────────────────────────────
CREATE TABLE clause_source (
    id                  SERIAL PRIMARY KEY,
    card_id             INTEGER NOT NULL REFERENCES card(id) ON DELETE CASCADE,
    doc_name            VARCHAR(200) NOT NULL,
    page_no             SMALLINT,
    content             TEXT NOT NULL,                -- 조항 원문
    embedding           vector(1536),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_clause_embedding ON clause_source
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50);

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
    income_day          SMALLINT NOT NULL             -- 급여일
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
    category            VARCHAR(40) NOT NULL,
    payment_type        VARCHAR(20) NOT NULL,         -- LUMP | INSTALLMENT | INTEREST_FREE
    installment_months  SMALLINT NOT NULL DEFAULT 0,
    is_recurring        BOOLEAN NOT NULL DEFAULT false
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
    card_id             INTEGER REFERENCES card(id)
);

CREATE INDEX idx_fixed_persona ON fixed_expense (persona_id, expense_type);
