import {
  formatDate,
  formatWon,
  PAYMENT_TYPE_LABEL,
  type RouteCandidate,
} from '../types/contract';

interface RouteCandidateCardProps {
  candidate: RouteCandidate;
  /** best 카드는 강조 배경(파란색)으로, 대안은 흰 배경으로 그린다. */
  highlight?: boolean;
}

export function RouteCandidateCard({ candidate, highlight = false }: RouteCandidateCardProps) {
  const {
    cardName,
    isDemo,
    payDate,
    paymentType,
    installmentMonths,
    expectedDiscount,
    perfAchieved,
    perfCurrent,
    perfRequired,
  } = candidate;

  return (
    <div
      className={
        highlight
          ? 'bg-blue-50 rounded-xl border border-blue-200 p-6'
          : 'bg-white rounded-xl border border-gray-200 p-6'
      }
    >
      <div className="flex items-start justify-between gap-4 mb-4">
        <div>
          <div className="flex items-center gap-2">
            <p className="text-lg font-semibold text-gray-900">{cardName}</p>
            {isDemo && <DemoBadge />}
          </div>
          <p className="text-xs text-gray-500 mt-1">{formatDate(payDate)} 결제 예정</p>
        </div>
        <span
          className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ${
            perfAchieved ? 'bg-emerald-50 text-emerald-600' : 'bg-amber-50 text-amber-600'
          }`}
        >
          {perfAchieved ? '실적 충족' : '실적 미충족'}
        </span>
      </div>

      <p className="text-3xl font-bold tabular-nums text-gray-900 mb-1">
        {formatWon(expectedDiscount)}
      </p>
      <p className="text-xs text-gray-500 mb-4">예상 할인액</p>

      <dl className="flex gap-6">
        <div>
          <dt className="text-xs text-gray-500 mb-1">결제 방식</dt>
          <dd className="text-sm text-gray-900">
            {PAYMENT_TYPE_LABEL[paymentType]}
            {installmentMonths > 0 && ` ${installmentMonths}개월`}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-gray-500 mb-1">실적(현재/필요)</dt>
          <dd className="text-sm text-gray-900 tabular-nums">
            {formatWon(perfCurrent)} / {formatWon(perfRequired)}
          </dd>
        </div>
      </dl>
    </div>
  );
}

// ui-system.md: "시연용 가상 카드에는 반드시 '시연용' 뱃지를 표시한다".
// newCardSuggestion에도 같은 규칙이 적용돼(isDemo 필드가 동일한 의미) 이
// 컴포넌트를 export해 RouteResultPage에서도 재사용한다.
export function DemoBadge() {
  return (
    <span className="inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium bg-gray-100 text-gray-600">
      시연용
    </span>
  );
}
