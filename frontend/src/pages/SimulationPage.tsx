import { useState, type FormEvent } from 'react';

import { ApiRequestError } from '../api/client';
import { MAX_QUERY_LENGTH, runSimulation } from '../api/simulate';
import { BalanceTrendChart } from '../components/BalanceTrendChart';
import { Button } from '../components/Button';
import { Skeleton } from '../components/Skeleton';
import {
  formatWon,
  PAYMENT_TYPE_LABEL,
  SCENARIO_LABEL,
  type SimulationResponse,
} from '../types/contract';

type RunState =
  | { status: 'idle' }
  | { status: 'running' }
  | { status: 'error'; message: string }
  | { status: 'done'; result: SimulationResponse };

interface SimulationPageProps {
  personaId: number;
}

export function SimulationPage({ personaId }: SimulationPageProps) {
  const [query, setQuery] = useState('');
  const [state, setState] = useState<RunState>({ status: 'idle' });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = query.trim();
    if (trimmed.length === 0) return;

    setState({ status: 'running' });
    runSimulation(personaId, trimmed)
      .then((result) => setState({ status: 'done', result }))
      .catch((err: unknown) => {
        const message =
          err instanceof ApiRequestError
            ? err.message
            : '시뮬레이션을 실행하지 못했습니다.';
        setState({ status: 'error', message });
      });
  };

  const running = state.status === 'running';

  return (
    <section className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-gray-900 mb-1">현금흐름 시뮬레이션</h3>
        <p className="text-sm text-gray-500">
          사려는 것을 그대로 물어보면 6개월 잔고 추이를 계산합니다.
        </p>
      </div>

      <form onSubmit={submit} className="space-y-2">
        <label className="block">
          <span className="sr-only">시뮬레이션 질의</span>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            maxLength={MAX_QUERY_LENGTH}
            disabled={running}
            placeholder="아이폰 180만원 할부로 사도 될까"
            className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:border-blue-600 focus:ring-1 focus:ring-blue-600 outline-none"
          />
        </label>
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-500">
            {query.length}/{MAX_QUERY_LENGTH}자
          </span>
          <Button type="submit" disabled={running || query.trim().length === 0}>
            {running ? '계산 중…' : '계산하기'}
          </Button>
        </div>
      </form>

      {running && (
        <div className="space-y-4">
          <Skeleton className="h-16 w-full rounded-xl" />
          <Skeleton className="h-72 w-full rounded-xl" />
          <p className="text-xs text-gray-500">
            질문을 해석하고 6개월치를 계산하는 중입니다.
          </p>
          </div>
      )}

      {state.status === 'error' && (
        <div className="bg-red-50 rounded-xl border border-red-200 p-6">
          <p className="text-sm text-red-600">{state.message}</p>
        </div>
      )}

      {state.status === 'done' && <SimulationResult result={state.result} />}
    </section>
  );
}

function SimulationResult({ result }: { result: SimulationResponse }) {
  const { parsed, scenarios, deadPoint, forecastMeta } = result;

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <p className="text-sm text-gray-500 mb-1">이렇게 이해했습니다</p>
        <p className="text-sm text-gray-900">
          <span className="tabular-nums font-semibold">{formatWon(parsed.amount)}</span>
          {' · '}
          {PAYMENT_TYPE_LABEL[parsed.paymentType]}
          {parsed.installmentMonths > 0 && ` ${parsed.installmentMonths}개월`}
        </p>
        {/* 카테고리는 spend_category 코드다. 이름표는 DB에만 있고 API로 나오지
            않아 코드를 그대로 보여준다. 화면에서 지어내면 마스터와 어긋난다. */}
        <p className="text-xs text-gray-500 mt-1">분류 {parsed.category}</p>
      </div>

      {deadPoint !== null ? (
        <div className="bg-red-50 rounded-xl border border-red-200 p-6">
          <p className="text-sm text-red-600">
            <span className="font-semibold">
              {SCENARIO_LABEL[deadPoint.level]} 시나리오에서 {deadPoint.month} 잔고가
              마이너스로 전환됩니다.
            </span>{' '}
            <span className="tabular-nums">{formatWon(deadPoint.shortage)}</span> 부족합니다.
          </p>
        </div>
      ) : (
        <div className="bg-emerald-50 rounded-xl border border-emerald-200 p-6">
          <p className="text-sm text-emerald-600">
            6개월 안에 잔고가 마이너스로 전환되는 시점이 없습니다.
          </p>
        </div>
      )}

      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h4 className="text-sm text-gray-900 mb-4">6개월 잔고 추이</h4>
        <BalanceTrendChart scenarios={scenarios} deadPoint={deadPoint} />
      </div>

      <p className="text-xs text-gray-500">
        최근 {forecastMeta.monthsUsed}개월, 거래 {forecastMeta.txnCount.toLocaleString('ko-KR')}건을
        근거로 계산했습니다.
        {forecastMeta.coldStart &&
          ' 표본이 적어 예측 폭이 실제와 다를 수 있습니다.'}
      </p>
    </div>
  );
}
