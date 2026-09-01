-- ═══════════════════════════════════════════════════════════
-- 시연용 페르소나 시드 데이터
--
-- 거래 내역(transaction)은 scripts/generate_persona.py 로 생성한다.
-- 이 파일은 페르소나 기본 정보와 확정 지출만 정의한다.
--
-- ⚠️ 전부 가상 인물이며 실제 개인의 금융 데이터가 아니다.
-- ═══════════════════════════════════════════════════════════

-- ─────────────────────────────────────────────
-- 1. 구독 과다형
--    표면 잔고는 여유 있어 보이나 구독이 잠식하는 유형
-- ─────────────────────────────────────────────
INSERT INTO persona (id, code, display_name, description, account_balance, monthly_income, income_day)
VALUES (1, 'SUBSCRIPTION_HEAVY', '구독이 쌓인 김넉넉',
        '스트리밍·음원·클라우드 등 구독 서비스를 다수 이용 중이며, 일부는 사용하지 않고 있다. 통장 잔고는 충분해 보이지만 매달 빠져나가는 고정비 비중이 크다.',
        2450000, 3200000, 25);

INSERT INTO persona_card (persona_id, card_id, payment_day) VALUES
(1, 1, 14),
(1, 3, 25);

INSERT INTO fixed_expense (persona_id, expense_type, label, amount, charge_day, remaining_months, last_used_date, card_id) VALUES
(1, 'SUBSCRIPTION', '영상 스트리밍 A',      17000,  5, NULL, '2026-08-14', 1),
(1, 'SUBSCRIPTION', '영상 스트리밍 B',      13500,  8, NULL, '2026-03-02', 1),
(1, 'SUBSCRIPTION', '음원 스트리밍',        10900, 11, NULL, '2026-08-15', 3),
(1, 'SUBSCRIPTION', '클라우드 스토리지',     11900, 15, NULL, '2026-08-10', 1),
(1, 'SUBSCRIPTION', '전자책 구독',           9900, 18, NULL, '2026-01-20', 3),
(1, 'SUBSCRIPTION', '커머스 멤버십',         4990, 22, NULL, '2026-08-15', 3),
(1, 'SUBSCRIPTION', '생산성 앱',            12000, 27, NULL, '2026-05-11', 1),
(1, 'INSURANCE',    '실손의료보험',         48000, 10, NULL, NULL,         NULL),
(1, 'LOAN',         '학자금 대출 상환',    180000, 20,   18, NULL,         NULL);

-- ─────────────────────────────────────────────
-- 2. 할부 누적형
--    할부가 겹쳐 향후 현금흐름이 빠듯해지는 유형
-- ─────────────────────────────────────────────
INSERT INTO persona (id, code, display_name, description, account_balance, monthly_income, income_day)
VALUES (2, 'INSTALLMENT_HEAVY', '할부가 겹친 이넉넉',
        '가전과 전자기기를 할부로 구매해 잔여 할부금이 누적되어 있다. 추가 소비 시 몇 달 뒤 잔고가 마이너스로 전환될 위험이 있다.',
        1600000, 2900000, 10);

INSERT INTO persona_card (persona_id, card_id, payment_day) VALUES
(2, 1, 25),
(2, 2, 14),
(2, 3, 5);

INSERT INTO fixed_expense (persona_id, expense_type, label, amount, charge_day, remaining_months, last_used_date, card_id) VALUES
(2, 'INSTALLMENT',  '노트북 12개월 할부',   145000, 25,    7, NULL,         1),
(2, 'INSTALLMENT',  '냉장고 24개월 할부',    72000, 14,   16, NULL,         2),
(2, 'INSTALLMENT',  '태블릿 6개월 할부',    118000,  5,    2, NULL,         3),
(2, 'INSTALLMENT',  '에어컨 6개월 할부',    348000, 20,    6, NULL,         1),
(2, 'LOAN',         '가전 구입 신용대출 상환', 530000, 28, 24, NULL,      NULL),
(2, 'SUBSCRIPTION', '영상 스트리밍 A',       17000,  7, NULL, '2026-08-13', 2),
(2, 'SUBSCRIPTION', '음원 스트리밍',         10900, 12, NULL, '2026-08-15', 2),
(2, 'INSURANCE',    '실손의료보험',          52000, 15, NULL, NULL,         NULL);

-- ─────────────────────────────────────────────
-- 3. 안정형
--    여유가 있어 최적화 여지를 보여주기 좋은 유형
-- ─────────────────────────────────────────────
INSERT INTO persona (id, code, display_name, description, account_balance, monthly_income, income_day)
VALUES (3, 'STABLE', '안정적인 박넉넉',
        '고정 지출이 적고 잔고에 여유가 있다. 다만 카드 실적 조건을 몰라 혜택을 놓치고 있어, 결제 카드와 시점만 조정해도 개선 여지가 크다.',
        4800000, 3800000, 25);

INSERT INTO persona_card (persona_id, card_id, payment_day) VALUES
(3, 1, 14),
(3, 2, 14),
(3, 3, 14);

INSERT INTO fixed_expense (persona_id, expense_type, label, amount, charge_day, remaining_months, last_used_date, card_id) VALUES
(3, 'SUBSCRIPTION', '영상 스트리밍 A',       17000,  5, NULL, '2026-08-15', 1),
(3, 'SUBSCRIPTION', '커머스 멤버십',          4990, 12, NULL, '2026-08-14', 2),
(3, 'INSURANCE',    '실손의료보험',          45000, 10, NULL, NULL,         NULL);

SELECT setval('persona_id_seq', 3, true);
