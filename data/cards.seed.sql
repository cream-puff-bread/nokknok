-- ═══════════════════════════════════════════════════════════
-- 시연용 카드 시드 데이터
--
-- ⚠️ 여기 정의된 카드는 실제 시판 상품이 아닌 가상 상품이다.
--    실제 카드사 상품 조건을 임의로 기재하면 사실과 다를 수 있으므로,
--    국내 신용카드의 전형적인 규칙 구조만 차용한 데모 상품으로 구성했다.
--
--    실제 카드로 교체할 경우:
--      1) 카드사 공식 상품 안내장(PDF) 원문에서 조건을 확인할 것
--      2) 블로그·카드 비교 사이트의 요약은 근거로 사용하지 말 것
--      3) is_demo를 false로 바꾸고 source_url에 출처를 기재할 것
--      4) clause_source에 근거 조항 원문을 함께 적재할 것
--
-- 세 카드는 서로 다른 규칙 구조를 갖도록 의도적으로 설계했다.
--   A: 계단형        — 실적 구간별 한도 차등. 구간 탐색·경계 판정 검증
--   B: 단일 조건형   — 기준 하나, 고정 할인율. 기본 판정 경로 검증
--   C: 제외 복잡형   — 제외 항목 다수. 제외 로직 정확성 검증
-- ═══════════════════════════════════════════════════════════

-- ─────────────────────────────────────────────
-- 카드 A : 계단형 (실적 구간별 한도 차등)
-- 전월 1일~말일 기준, 결제일 무관
-- ─────────────────────────────────────────────
INSERT INTO card (id, issuer, name, perf_period_type, billing_close_day, monthly_cap, is_demo)
VALUES (1, '넉넉카드', 'NOKKNOK A (계단형)', 'MONTH_START', NULL, 50000, true);

-- 30만 이상 50만 미만
INSERT INTO card_benefit_rule (card_id, perf_min, perf_max, category, discount_rate, category_cap, verified) VALUES
(1, 300000,  500000, 'DINING',    0.0500, 10000, true),
(1, 300000,  500000, 'ONLINE',    0.0300,  8000, true),
(1, 300000,  500000, 'TRANSPORT', 0.0500,  5000, true);

-- 50만 이상 100만 미만
INSERT INTO card_benefit_rule (card_id, perf_min, perf_max, category, discount_rate, category_cap, verified) VALUES
(1, 500000, 1000000, 'DINING',    0.0700, 20000, true),
(1, 500000, 1000000, 'ONLINE',    0.0500, 15000, true),
(1, 500000, 1000000, 'TRANSPORT', 0.0700, 10000, true);

-- 100만 이상
INSERT INTO card_benefit_rule (card_id, perf_min, perf_max, category, discount_rate, category_cap, verified) VALUES
(1, 1000000, NULL,   'DINING',    0.1000, 30000, true),
(1, 1000000, NULL,   'ONLINE',    0.0700, 20000, true),
(1, 1000000, NULL,   'TRANSPORT', 0.1000, 15000, true);

INSERT INTO card_exclusion (card_id, exclusion_type, target_kind, target_value, verified) VALUES
(1, 'BOTH',        'PAYMENT_TYPE', 'INTEREST_FREE', true),
(1, 'PERFORMANCE', 'CATEGORY',     'TAX',           true);


-- ─────────────────────────────────────────────
-- 카드 B : 단일 조건형 (기준 하나, 고정 할인율)
-- 청구 마감일 기준이므로 결제일 변경 시 실적 집계 기간이 달라진다
-- ─────────────────────────────────────────────
INSERT INTO card (id, issuer, name, perf_period_type, billing_close_day, monthly_cap, is_demo)
VALUES (2, '넉넉카드', 'NOKKNOK B (단일 조건형)', 'BILLING_CYCLE', 14, 30000, true);

INSERT INTO card_benefit_rule (card_id, perf_min, perf_max, category, discount_rate, category_cap, verified) VALUES
(2, 400000, NULL, 'ALL', 0.0200, 30000, true);

INSERT INTO card_exclusion (card_id, exclusion_type, target_kind, target_value, verified) VALUES
(2, 'BOTH', 'PAYMENT_TYPE', 'INTEREST_FREE', true),
(2, 'BOTH', 'CATEGORY',     'GIFT_CARD',     true);


-- ─────────────────────────────────────────────
-- 카드 C : 제외 항목 복잡형
-- 할인율은 높지만 실적 제외 항목이 많아 조건 충족이 까다롭다
-- ─────────────────────────────────────────────
INSERT INTO card (id, issuer, name, perf_period_type, billing_close_day, monthly_cap, is_demo)
VALUES (3, '넉넉카드', 'NOKKNOK C (제외 복잡형)', 'MONTH_START', NULL, 40000, true);

INSERT INTO card_benefit_rule (card_id, perf_min, perf_max, category, discount_rate, category_cap, verified) VALUES
(3, 300000, NULL, 'ONLINE',   0.1000, 20000, true),
(3, 300000, NULL, 'DELIVERY', 0.1500, 10000, true),
(3, 300000, NULL, 'CAFE',     0.1000, 10000, true);

-- 실적에서 빠지는 항목 (할인은 별개)
INSERT INTO card_exclusion (card_id, exclusion_type, target_kind, target_value, verified) VALUES
(3, 'PERFORMANCE', 'CATEGORY',     'TAX',            true),
(3, 'PERFORMANCE', 'CATEGORY',     'UTILITY',        true),
(3, 'PERFORMANCE', 'CATEGORY',     'GIFT_CARD',      true),
(3, 'PERFORMANCE', 'CATEGORY',     'INSURANCE',      true),
(3, 'PERFORMANCE', 'CATEGORY',     'EDUCATION',      true),
(3, 'PERFORMANCE', 'PAYMENT_TYPE', 'INTEREST_FREE',  true),
-- 할인에서만 빠지는 항목
(3, 'DISCOUNT',    'CATEGORY',     'TRANSPORT',      true);


SELECT setval('card_id_seq', 3, true);
