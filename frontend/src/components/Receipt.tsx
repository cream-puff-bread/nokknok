import { ClauseList } from './ClauseList';
import { Skeleton } from './Skeleton';
import {
  formatWon,
  PAYMENT_TYPE_LABEL,
  SCENARIO_LABEL,
  type DeadPoint,
  type ParsedQuery,
  type RouteResponse,
} from '../types/contract';

interface ReceiptProps {
  purchase: ParsedQuery;
  categoryLabel: (code: string) => string;
  /** 어느 카드로 결제할지. 아직 계산 중이면 loading 을 켠다. */
  route?: RouteResponse | null;
  routeLoading?: boolean;
  /** 결제 후 잔고가 어떻게 되는지. 없으면 그 칸을 그리지 않는다. */
  deadPoint?: DeadPoint | null;
  forecastLoaded?: boolean;
  forecastLoading?: boolean;
}

/**
 * 결제 영수증.
 *
 * 추천 결과와 잔고 영향을 표 두 개로 나눠 놓으면 이용자가 둘을 머릿속에서
 * 합쳐야 한다. 영수증 한 장에 "얼마를", "어느 카드로", "그래서 잔고가
 * 어떻게 되는지" 를 세로로 쌓으면 그 자리에서 판단이 끝난다.
 *
 * 근거 약관을 맨 아래 작은 글씨로 두는 것도 형식과 내용이 맞아떨어진다 —
 * 실제 영수증의 약관 자리에 진짜 약관 조항이 들어간다. 다른 도구는 할인액
 * 까지는 내놓아도 이 칸을 채우지 못한다.
 */
export function Receipt({
  purchase,
  categoryLabel,
  route,
  routeLoading = false,
  deadPoint,
  forecastLoaded = false,
  forecastLoading = false,
}: ReceiptProps) {
  const best = route?.best ?? null;

  return (
    <article className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <header className="px-6 py-4 border-b border-dashed border-gray-300">
        <p className="text-xs text-gray-500">결제 시뮬레이션</p>
      </header>

      <dl className="px-6 py-4 space-y-3 border-b border-dashed border-gray-300">
        <Row label="결제 금액">
          <span className="text-lg font-bold tabular-nums">{formatWon(purchase.amount)}</span>
        </Row>
        <Row label="분류">{categoryLabel(purchase.category)}</Row>
        <Row label="결제 방식">
          {PAYMENT_TYPE_LABEL[purchase.paymentType]}
          {purchase.installmentMonths > 0 && ` ${purchase.installmentMonths}개월`}
        </Row>
      </dl>

      <dl className="px-6 py-4 space-y-3 border-b border-dashed border-gray-300">
        {routeLoading && (
          <>
            <Row label="추천 카드">
              <Skeleton className="h-4 w-40" />
            </Row>
            <Row label="예상 할인">
              <Skeleton className="h-4 w-20" />
            </Row>
          </>
        )}
        {best && (
          <>
            <Row label="추천 카드">
              <span className="font-medium">{best.cardName}</span>
              {best.isDemo && (
                <span className="ml-2 inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium bg-gray-100 text-gray-500">
                  시연용
                </span>
              )}
            </Row>
            <Row label="실적">
              <span className="tabular-nums">
                {formatWon(best.perfCurrent)} / {formatWon(best.perfRequired)}
              </span>
              <span
                className={`ml-2 text-xs ${
                  best.perfAchieved ? 'text-emerald-600' : 'text-amber-600'
                }`}
              >
                {best.perfAchieved ? '충족' : '미충족'}
              </span>
            </Row>
            <Row label="예상 할인">
              <span className="text-lg font-bold tabular-nums text-blue-600">
                −{formatWon(best.expectedDiscount)}
              </span>
            </Row>
          </>
        )}
        {!routeLoading && !best && (
          <p className="text-sm text-gray-500">추천할 카드를 찾지 못했습니다.</p>
        )}
      </dl>

      {(forecastLoading || forecastLoaded) && (
        <div className="px-6 py-4 border-b border-dashed border-gray-300">
          {forecastLoading ? (
            <Skeleton className="h-4 w-64" />
          ) : deadPoint ? (
            // 이 서비스가 존재하는 이유가 이 한 줄이다. 할인만 보고 결제하면
            // 놓치는 것을 여기서 잡는다.
            <p className="text-sm text-red-600">
              결제 후 <span className="font-semibold">{formatMonth(deadPoint.month)}</span> 잔고가{' '}
              <span className="tabular-nums font-semibold">{formatWon(deadPoint.shortage)}</span>{' '}
              부족해집니다
              <span className="text-gray-500">
                {' '}
                ({SCENARIO_LABEL[deadPoint.level]} 시나리오)
              </span>
            </p>
          ) : (
            <p className="text-sm text-emerald-600">
              결제해도 6개월 안에 잔고가 마이너스로 가지 않습니다
            </p>
          )}
        </div>
      )}

      {best && best.clauses.length > 0 && (
        // 영수증 하단 약관 자리에 진짜 약관 조항이 들어간다.
        <footer className="px-6 py-4 bg-gray-50">
          <ClauseList clauses={best.clauses} />
        </footer>
      )}
    </article>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className="text-sm text-gray-500 shrink-0">{label}</dt>
      <dd className="text-sm text-gray-900 text-right">{children}</dd>
    </div>
  );
}

/** '2026-09' 을 '9월' 로. 차트 축과 표기를 맞춘다(ui-system.md). */
function formatMonth(month: string): string {
  const parsed = Number(month.slice(5, 7));
  return Number.isNaN(parsed) ? month : `${parsed}월`;
}
