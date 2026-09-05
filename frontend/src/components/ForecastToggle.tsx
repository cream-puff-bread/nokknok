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
 * 차트에 겹쳐 그릴 대안은 늘 하나다 — 여럿을 점선으로 깔면 무엇과 무엇을
 * 견주는지 흐려진다. 기준은 일시불로 두고, 일시불을 고른 동안에는 가장 짧은
 * 할부를 대안으로 보여준다.
 */
const BASE_VARIANTS: Variant[] = [
  { key: 'LUMP', label: '일시불', paymentType: 'LUMP', installmentMonths: 0 },
  { key: 'FREE3', label: '무이자 3개월', paymentType: 'INTEREST_FREE', installmentMonths: 3 },
  { key: 'FREE6', label: '무이자 6개월', paymentType: 'INTEREST_FREE', installmentMonths: 6 },
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
      ];

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
  // 비교 대상은 늘 일시불이다. 일시불을 보고 있을 때만 가장 짧은 할부를
  // 대신 깐다 — "나눠 내면 어떻게 달라지나" 가 이 화면의 질문이라서다.
  const other =
    (active.key === 'LUMP'
      ? variants.find((v) => v.key !== 'LUMP')
      : variants.find((v) => v.key === 'LUMP')) ?? null;
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
  // 보통 시나리오가 어디까지 내려가는지 함께 말한다.
  //
  // "가장 빠듯한 경우에만 부족하다" 로만 적었더니, 보통 선이 2만원까지
  // 떨어져 눈으로는 0원에 붙어 있는데 글은 버틴다고 말해 서로 어긋났다.
  // 30만원이 2만원이 되는 것은 버티는 게 아니다.
  const trough = lowestPoint(shown, 'NORMAL');

  // 보통 시나리오까지 마이너스면 경고(빨강), 빠듯한 경우에만 마이너스면
  // 주의(호박)다 — ui-system.md 의 색 배정 그대로다. 늘 호박으로 두면 보통
  // 시나리오가 적자인 날에도 "조심하세요" 수준으로 읽힌다.
  const severe = trough !== null && trough.balance < 0;
  const tone = severe
    ? { box: 'border-red-200 bg-red-50', head: 'text-red-700', body: 'text-red-700/80' }
    : { box: 'border-amber-200 bg-amber-50', head: 'text-amber-900', body: 'text-amber-900/80' };

  return (
    <div className={`mt-3 rounded-2xl border p-4 ${tone.box}`}>
      <p className={`text-sm font-semibold ${tone.head}`}>
        {severe ? '🚨' : '⚠️'} {active.label} 결제 시{' '}
        {monthIndex === null ? '' : `${monthIndex}개월 뒤 `}
        잔고 {severe ? '부족' : '주의'}
      </p>
      <p className={`mt-1 text-xs ${tone.body}`}>
        {/* 남는 쪽은 "줄어든다" 고 쓰지 않는다. 6개월 할부처럼 가장 낮은
            달의 잔고가 오늘보다 오히려 많은 경우가 있어서, 방향을 단정하면
            그 화면에서 거짓말이 된다. 가장 낮은 지점만 사실대로 짚는다. */}
        {trough !== null && trough.balance < 0
          ? `보통 시나리오에서도 ${trough.index}개월 뒤 ${formatWon(-trough.balance)} 모자랍니다. `
          : trough !== null
            ? `보통 시나리오는 ${trough.index}개월 뒤 ${formatWon(trough.balance)}이 가장 낮습니다. `
            : ''}
        가장 빠듯한 경우에는 {formatWon(shown.deadPoint.shortage)} 부족해집니다.
        {/* 일시불은 나눠 내는 방법이 아니다. 할부를 보고 있는데 더 나은
            쪽이 없으면 굳이 다른 방식을 권하지 않는다. */}
        {other !== null &&
          other.installmentMonths > 0 &&
          (saferIsSafe
            ? ` ${other.label}로 나눠 내면 6개월 내내 0원 아래로 내려가지 않습니다.`
            : ` ${other.label}로 나눠 내면 그 시점을 뒤로 미룰 수 있습니다.`)}
      </p>
    </div>
  );
}

function keyOf(paymentType: PaymentType, months: number): string {
  if (paymentType === 'LUMP') return 'LUMP';
  if (paymentType === 'INTEREST_FREE' && (months === 3 || months === 6)) {
    return `FREE${months}`;
  }
  return `${paymentType}${months}`;
}

/** 적자 달이 지금부터 몇 번째인지. 못 찾으면 null. */
function indexOf(simulation: SimulationResponse, month: string): number | null {
  const months = simulation.scenarios[0]?.points.map((p) => p.month) ?? [];
  const index = months.indexOf(month);
  return index < 0 ? null : index + 1;
}

/** 그 시나리오에서 잔고가 가장 낮아지는 지점. 없으면 null. */
function lowestPoint(
  simulation: SimulationResponse,
  level: string,
): { index: number; balance: number } | null {
  const points = simulation.scenarios.find((s) => s.level === level)?.points ?? [];
  if (points.length === 0) return null;
  let best = 0;
  for (let i = 1; i < points.length; i += 1) {
    if (points[i].balance < points[best].balance) best = i;
  }
  return { index: best + 1, balance: points[best].balance };
}
