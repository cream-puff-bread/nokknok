// 넉넉(nokknok) 프론트엔드 공용 타입
// contracts/api-spec.yaml과 1:1 대응. 임의 변경 금지.
// 변경이 필요하면 api-spec.yaml을 먼저 고치고 전원에게 공유한다.

export type ScenarioLevel = 'COMFORTABLE' | 'NORMAL' | 'TIGHT';
export type PaymentType = 'LUMP' | 'INSTALLMENT' | 'INTEREST_FREE';
export type ExpenseType = 'SUBSCRIPTION' | 'INSTALLMENT' | 'LOAN' | 'INSURANCE';
export type PersonaCode = 'SUBSCRIPTION_HEAVY' | 'INSTALLMENT_HEAVY' | 'STABLE';

/** 화면 표기용 라벨. 내부 용어(낙관/기본/비관)는 절대 노출하지 않는다. */
export const SCENARIO_LABEL: Record<ScenarioLevel, string> = {
  COMFORTABLE: '여유',
  NORMAL: '보통',
  TIGHT: '빠듯',
};

/** 시나리오별 차트 색상. ui-system.md와 동일하게 유지한다. */
export const SCENARIO_COLOR: Record<ScenarioLevel, string> = {
  COMFORTABLE: '#10b981', // emerald-500
  NORMAL: '#2563eb',      // blue-600
  TIGHT: '#f59e0b',       // amber-500
};

export interface Persona {
  id: number;
  code: PersonaCode;
  displayName: string;
  description: string;
  accountBalance: number;
  cardCount: number;
}

export interface FixedExpense {
  label: string;
  amount: number;
  chargeDay: number;
  expenseType: ExpenseType;
  unusedSuspect: boolean;
}

export interface BalanceResponse {
  accountBalance: number;
  fixedTotal: number;
  availableBalance: number;
  fixedExpenses: FixedExpense[];
}

export interface ScenarioPoint {
  /** 'YYYY-MM' */
  month: string;
  balance: number;
}

export interface Scenario {
  level: ScenarioLevel;
  points: ScenarioPoint[];
}

export interface DeadPoint {
  month: string;
  level: ScenarioLevel;
  shortage: number;
}

export interface ForecastMeta {
  monthsUsed: number;
  txnCount: number;
  coldStart: boolean;
}

export interface ParsedQuery {
  amount: number;
  paymentType: PaymentType;
  installmentMonths: number;
  category: string;
}

export interface SimulationResponse {
  parsed: ParsedQuery;
  scenarios: Scenario[];
  /** 적자 전환 시점이 없으면 null */
  deadPoint: DeadPoint | null;
  forecastMeta: ForecastMeta;
}

export interface ClauseRef {
  content: string;
  docName: string;
  pageNo: number;
}

export interface RouteOption {
  cardId: number;
  cardName: string;
  /** 'YYYY-MM-DD' */
  payDate: string;
  paymentType: PaymentType;
  installmentMonths: number;
  expectedDiscount: number;
  perfAchieved: boolean;
  perfCurrent: number;
  perfRequired: number;
  /**
   * LLM 생성 설명. 생성 실패 시 null.
   * null이어도 나머지 계산 결과는 반드시 화면에 표시한다.
   * 설명이 없다고 결과 전체를 숨기지 않는다.
   */
  explanation: string | null;
  clauses: ClauseRef[];
}

export interface NewCardSuggestion {
  cardName: string;
  expectedGain: number;
  isAffiliate: boolean;
}

export interface ComputeMeta {
  candidatesTotal: number;
  candidatesPruned: number;
  elapsedMs: number;
}

export interface RouteResponse {
  best: RouteOption;
  alternatives: RouteOption[];
  /**
   * 보유 카드로 조건 충족 불가 시에만 존재.
   * 최적화 결과와 시각적으로 분리해 표시하고 제휴 여부를 함께 밝힌다.
   */
  newCardSuggestion: NewCardSuggestion | null;
  computeMeta: ComputeMeta;
}

export interface ApiError {
  code: string;
  message: string;
}

/** 금액 표기. 프론트에서 허용되는 유일한 금액 가공이다. */
export const formatWon = (v: number): string =>
  `${v.toLocaleString('ko-KR')}원`;

/** 차트 축 표기용 만원 단위 축약. */
export const formatManwon = (v: number): string =>
  `${Math.round(v / 10000).toLocaleString('ko-KR')}만`;

/** 'YYYY-MM-DD' -> 'M월 D일' */
export const formatDate = (iso: string): string => {
  const [, m, d] = iso.split('-');
  return `${Number(m)}월 ${Number(d)}일`;
};
