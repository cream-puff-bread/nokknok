import { useCallback, useEffect, useState } from 'react';

import { runSimulationForPurchase } from '../api/simulate';
import { ForecastChart } from './ForecastChart';
import { Skeleton } from './Skeleton';
import {
  formatWon,
  PAYMENT_TYPE_LABEL,
  type ParsedQuery,
  type PaymentType,
  type SimulationResponse,
} from '../types/contract';

interface Variant {
  key: string;
  label: string;
  paymentType: PaymentType;
  installmentMonths: number;
}

/**
 * 비교할 결제 방식.
 *
 * 엔진은 할인액만 최대화하므로 무이자 할부를 절대 고르지 않는다 — 제외 규칙은
 * 할인을 줄이기만 하기 때문이다(#33 리뷰). 그렇다고 "나눠 내면 언제까지
 * 버티는지" 가 무의미한 건 아니다. 엔진이 고르게 하는 대신 여기서 나란히
 * 놓고 사람이 고르게 한다.
 *
 * 둘로 좁힌 이유는 한 번에 견줄 수 있는 것이 둘까지이기 때문이다. 셋을
 * 늘어놓으면 무엇과 무엇을 비교하는지가 흐려지고, 차트에 겹쳐 그릴 대안도
 * 하나로 정해지지 않는다.
 */
const BASE_VARIANTS: Variant[] = [
  { key: 'LUMP', label: '일시불', paymentType: 'LUMP', installmentMonths: 0 },
  { key: 'FREE3', label: '무이자 3개월', paymentType: 'INTEREST_FREE', installmentMonths: 3 },
];

interface ForecastToggleProps {
  personaId: number;
  purchase: ParsedQuery;
  /** 물어본 방식으로 이미 계산해 둔 결과. 다시 부르지 않는다. */
  asked: SimulationResponse;
  /** 오늘의 가용잔고. 차트 첫 점('지금')으로 쓴다. */
  availableBalance?: number;
}

export function ForecastToggle({
  personaId,
  purchase,
  asked,
  availableBalance,
}: ForecastToggleProps) {
  const askedKey = keyOf(purchase.paymentType, purchase.installmentMonths);
  // 물어본 방식이 기본 후보에 없으면(예: 유이자 6개월 할부) 그것을 살리고
  // 대비되는 쪽 하나만 남긴다. 물어본 조건을 화면에서 지우지 않는다.
  const variants: Variant[] = BASE_VARIANTS.some((v) => v.key === askedKey)
    ? BASE_VARIANTS
    : [
        {
          key: askedKey,
          label: `${PAYMENT_TYPE_LABEL[purchase.paymentType]}${
            purchase.installmentMonths > 0 ? ` ${purchase.installmentMonths}개월` : ''
          }`,
          paymentType: purchase.paymentType,
          installmentMonths: purchase.installmentMonths,
        },
        ...BASE_VARIANTS.filter((v) => v.paymentType !== purchase.paymentType),
      ].slice(0, 2);

  const [activeKey, setActiveKey] = useState(askedKey);
  const [cache, setCache] = useState<Record<string, SimulationResponse>>({
    [askedKey]: asked,
  });
  const [loadingKey, setLoadingKey] = useState<string | null>(null);

  const load = useCallback(
    (variant: Variant) => {
      if (cache[variant.key] !== undefined) return;
      setLoadingKey(variant.key);
      runSimulationForPurchase(personaId, {
        ...purchase,
        paymentType: variant.paymentType,
        installmentMonths: variant.installmentMonths,
      })
        .then((result) => setCache((prev) => ({ ...prev, [variant.key]: result })))
        .catch(() => undefined)
        .finally(() => setLoadingKey(null));
    },
    [cache, personaId, purchase],
  );

  // 다른 방식도 미리 받아 둔다. 차트에 점선으로 겹쳐 그리려면 고르기 전부터
  // 값이 있어야 하고, 아래 안내 문구가 "바꾸면 괜찮아진다" 를 말하려면 그쪽
  // 결과를 알아야 한다. 구조화 입력이라 LLM 을 타지 않는다.
  useEffect(() => {
    for (const variant of variants) load(variant);
    // 최초 1회만. cache 를 의존성에 넣으면 채워질 때마다 다시 돈다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const active = variants.find((v) => v.key === activeKey) ?? variants[0];
  const other = variants.find((v) => v.key !== activeKey) ?? null;
  const shown = cache[active.key] ?? null;
  const otherForecast = other === null ? null : (cache[other.key] ?? null);

  return (
    <div>
      <div
        role="radiogroup"
        aria-label="결제 방식"
        className="mb-4 flex rounded-full bg-gray-100 p-1"
      >
        {variants.map((variant) => {
          const selected = variant.key === activeKey;
          return (
            <button
              key={variant.key}
              type="button"
              role="radio"
              aria-checked={selected}
              onClick={() => {
                setActiveKey(variant.key);
                load(variant);
              }}
              className={`flex-1 rounded-full py-2 text-sm transition-colors ${
                selected
                  ? 'bg-white font-bold text-gray-900 shadow-sm'
                  : 'text-gray-500 hover:text-gray-900'
              }`}
            >
              {variant.label}
            </button>
          );
        })}
      </div>

      {shown === null ? (
        <Skeleton className="h-60 w-full rounded-2xl" />
      ) : (
        <>
          <ForecastChart
            scenarios={shown.scenarios}
            deadPoint={shown.deadPoint}
            alternative={
              other !== null && otherForecast !== null
                ? { label: other.label, scenarios: otherForecast.scenarios }
                : null
            }
            startBalance={availableBalance}
          />

          <FeedbackBanner
            purchase={purchase}
            active={active}
            shown={shown}
            other={other}
            otherForecast={otherForecast}
          />
        </>
      )}

      {loadingKey !== null && loadingKey !== active.key && (
        <p className="mt-2 text-center text-[11px] text-gray-400">
          다른 방식을 계산하는 중입니다
        </p>
      )}
    </div>
  );
}

/**
 * 차트 아래 한 줄 결론.
 *
 * 그래프만으로는 "그래서 어떻게 하라는 건지" 가 안 나온다. 위험하면 무엇을
 * 바꾸면 되는지까지 말해야 다음 행동을 정할 수 있다 — 특히 옆에서 설명해 줄
 * 사람이 없는 화면에서는.
 */
function FeedbackBanner({
  purchase,
  active,
  shown,
  other,
  otherForecast,
}: {
  purchase: ParsedQuery;
  active: Variant;
  shown: SimulationResponse;
  other: Variant | null;
  otherForecast: SimulationResponse | null;
}) {
  if (shown.deadPoint === null) {
    const monthly =
      active.installmentMonths > 0
        ? Math.round(purchase.amount / active.installmentMonths)
        : null;
    return (
      <div className="mt-3 rounded-2xl border border-emerald-100 bg-emerald-50 p-4">
        <p className="text-sm font-semibold text-emerald-900">
          🛡️ {active.label}이면 6개월 내내 안전
        </p>
        <p className="mt-1 text-xs text-emerald-900/80">
          {monthly === null
            ? '6개월 동안 잔고가 0원 아래로 내려가지 않습니다.'
            : `월 ${formatWon(monthly)}씩 나눠 내면 잔고가 0원 위를 유지합니다. 무이자라 이자 부담은 없습니다.`}
        </p>
      </div>
    );
  }

  const monthIndex = indexOf(shown, shown.deadPoint.month);
  const saferIsSafe = otherForecast !== null && otherForecast.deadPoint === null;

  return (
    <div className="mt-3 rounded-2xl border border-red-100 bg-red-50 p-4">
      <p className="text-sm font-semibold text-red-900">
        ⚠️ {active.label} 결제 시 {monthIndex === null ? '' : `+${monthIndex}개월 `}잔고 위기
      </p>
      <p className="mt-1 text-xs text-red-900/80">
        빠듯 시나리오에서 잔고가 {formatWon(shown.deadPoint.shortage)} 부족해집니다.
        {other !== null &&
          (saferIsSafe
            ? ` ${other.label}로 나눠 내면 6개월 내내 0원 아래로 내려가지 않습니다.`
            : ` ${other.label}로 나눠 내면 그 시점을 뒤로 미룰 수 있습니다.`)}
      </p>
    </div>
  );
}

function keyOf(paymentType: PaymentType, months: number): string {
  if (paymentType === 'LUMP') return 'LUMP';
  return paymentType === 'INTEREST_FREE' && months === 3 ? 'FREE3' : `${paymentType}${months}`;
}

/** 적자 달이 지금부터 몇 번째인지. 못 찾으면 null. */
function indexOf(simulation: SimulationResponse, month: string): number | null {
  const months = simulation.scenarios[0]?.points.map((p) => p.month) ?? [];
  const index = months.indexOf(month);
  return index < 0 ? null : index + 1;
}
