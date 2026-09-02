import { useCallback, useEffect, useState } from 'react';

import { ApiRequestError } from '../api/client';
import { runSimulationForPurchase } from '../api/simulate';
import { BalanceTrendChart } from './BalanceTrendChart';
import { Skeleton } from './Skeleton';
import {
  formatWon,
  PAYMENT_TYPE_LABEL,
  SCENARIO_LABEL,
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
 * 나눠 낼 후보. 총액은 같고 월 부담만 달라진다.
 *
 * 엔진은 할인액만 최대화하므로 무이자 할부를 절대 고르지 않는다 — 제외 규칙은
 * 할인을 줄이기만 하기 때문이다(#33 리뷰). 그렇다고 "나눠 내면 언제까지
 * 버티는지" 가 무의미한 건 아니다. 엔진이 고르게 하는 대신 여기서 나란히
 * 보여주고 사람이 고르게 한다.
 */
const SPLIT_VARIANTS: Variant[] = [
  { key: 'LUMP', label: '일시불', paymentType: 'LUMP', installmentMonths: 0 },
  {
    key: 'FREE3',
    label: '무이자 3개월',
    paymentType: 'INTEREST_FREE',
    installmentMonths: 3,
  },
  {
    key: 'FREE6',
    label: '무이자 6개월',
    paymentType: 'INTEREST_FREE',
    installmentMonths: 6,
  },
];

const ASKED_KEY = 'ASKED';

interface ForecastToggleProps {
  personaId: number;
  /** 이용자가 물어본 그대로의 구매. */
  purchase: ParsedQuery;
  /** 물어본 방식으로 이미 계산해 둔 결과. 다시 부르지 않는다. */
  asked: SimulationResponse;
}

export function ForecastToggle({ personaId, purchase, asked }: ForecastToggleProps) {
  const askedVariant: Variant = {
    key: ASKED_KEY,
    label: `${PAYMENT_TYPE_LABEL[purchase.paymentType]}${
      purchase.installmentMonths > 0 ? ` ${purchase.installmentMonths}개월` : ''
    }`,
    paymentType: purchase.paymentType,
    installmentMonths: purchase.installmentMonths,
  };

  // 물어본 방식과 겹치는 후보는 뺀다 — 같은 계산을 두 번 보여줄 이유가 없다.
  const variants = [
    askedVariant,
    ...SPLIT_VARIANTS.filter(
      (v) =>
        !(
          v.paymentType === purchase.paymentType &&
          v.installmentMonths === purchase.installmentMonths
        ),
    ),
  ];

  const [activeKey, setActiveKey] = useState(ASKED_KEY);
  const [cache, setCache] = useState<Record<string, SimulationResponse>>({
    [ASKED_KEY]: asked,
  });
  const [loadingKey, setLoadingKey] = useState<string | null>(null);
  const [failedKey, setFailedKey] = useState<string | null>(null);

  const select = useCallback(
    (variant: Variant) => {
      setActiveKey(variant.key);
      setFailedKey(null);
      if (cache[variant.key] !== undefined) return;

      setLoadingKey(variant.key);
      runSimulationForPurchase(personaId, {
        ...purchase,
        paymentType: variant.paymentType,
        installmentMonths: variant.installmentMonths,
      })
        .then((result) => setCache((prev) => ({ ...prev, [variant.key]: result })))
        .catch((err: unknown) => {
          setFailedKey(variant.key);
          if (!(err instanceof ApiRequestError)) return;
        })
        .finally(() => setLoadingKey(null));
    },
    [cache, personaId, purchase],
  );

  // 물어본 방식이 적자로 끝나면 나머지 방식도 미리 계산해 둔다.
  //
  // 눌러 봐야 알 수 있으면 "나눠 내면 몇 달을 번다" 는 사실을 아무도 발견하지
  // 못한다 — URL 만 받아 혼자 둘러보는 사람에게는 특히 그렇다. 결과를 버튼에
  // 바로 적어 두면 누르기 전에 비교가 끝난다.
  //
  // 구조화 입력이라 LLM 을 타지 않아 한 건에 1초가 안 걸린다.
  useEffect(() => {
    if (asked.deadPoint === null) return;
    for (const variant of variants) {
      if (variant.key === ASKED_KEY) continue;
      runSimulationForPurchase(personaId, {
        ...purchase,
        paymentType: variant.paymentType,
        installmentMonths: variant.installmentMonths,
      })
        .then((result) => setCache((prev) => ({ ...prev, [variant.key]: result })))
        .catch(() => undefined);
    }
    // 최초 1회만 돈다. cache 를 의존성에 넣으면 채워질 때마다 다시 돈다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const active = cache[activeKey] ?? null;
  const loading = loadingKey === activeKey;

  return (
    <section>
      <h4 className="text-xs text-gray-500 mb-2">향후 6개월 잔고</h4>

      <div
        role="radiogroup"
        aria-label="결제 방식"
        className="mb-3 inline-flex rounded-xl bg-gray-100 p-1"
      >
        {variants.map((variant) => {
          const selected = variant.key === activeKey;
          const forecast = cache[variant.key];
          return (
            <button
              key={variant.key}
              type="button"
              role="radio"
              aria-checked={selected}
              onClick={() => select(variant)}
              className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                selected ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-900'
              }`}
            >
              {variant.label}
              {/* 결과를 버튼에 적어 둔다. 나눠 내면 적자가 사라지는지, 아니면
                  몇 달 뒤로 밀리는지가 누르기 전에 보여야 비교가 된다. */}
              {forecast !== undefined && (
                <span
                  className={`ml-1.5 text-xs ${
                    forecast.deadPoint === null ? 'text-emerald-600' : 'text-amber-600'
                  }`}
                >
                  {forecast.deadPoint === null
                    ? '안전'
                    : `${formatMonth(forecast.deadPoint.month)} 적자`}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {loading && <Skeleton className="h-56 w-full rounded-xl" />}

      {!loading && failedKey === activeKey && (
        <p className="text-sm text-gray-500">이 방식은 계산하지 못했습니다.</p>
      )}

      {!loading && active !== null && (
        <>
          {active.deadPoint === null ? (
            <p className="mb-3 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-600">
              이 방식이면 6개월 내내 잔고가 마이너스로 가지 않습니다.
            </p>
          ) : (
            <p className="mb-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
              <span className="font-semibold">{formatMonth(active.deadPoint.month)}</span> 잔고가{' '}
              <span className="tabular-nums font-semibold">
                {formatWon(active.deadPoint.shortage)}
              </span>{' '}
              부족해집니다
              <span className="text-gray-500"> ({SCENARIO_LABEL[active.deadPoint.level]} 시나리오)</span>
            </p>
          )}

          <BalanceTrendChart scenarios={active.scenarios} deadPoint={active.deadPoint} />
        </>
      )}
    </section>
  );
}

/** '2026-09' 을 '9월' 로. 차트 축과 표기를 맞춘다(ui-system.md). */
function formatMonth(month: string): string {
  const parsed = Number(month.slice(5, 7));
  return Number.isNaN(parsed) ? month : `${parsed}월`;
}
