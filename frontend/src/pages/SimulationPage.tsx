import { useCallback, useState, type FormEvent } from 'react';

import {
  ApiRequestError,
  SLOW_REQUEST_MESSAGE,
  type SlowRequestPhase,
} from '../api/client';
import { useCategoryLabels } from '../api/categories';
import { MAX_QUERY_LENGTH, runSimulation } from '../api/simulate';
import { BalanceTrendChart } from '../components/BalanceTrendChart';
import { Button } from '../components/Button';
import { ErrorState } from '../components/ErrorState';
import { PersonaNotFoundAction } from '../components/PersonaNotFoundAction';
import { Skeleton } from '../components/Skeleton';
import {
  formatWon,
  PAYMENT_TYPE_LABEL,
  type ApiErrorCode,
  SCENARIO_LABEL,
  type DeadPoint,
  type Scenario,
  type SimulationResponse,
} from '../types/contract';

type RunState =
  | { status: 'idle' }
  | { status: 'running' }
  | { status: 'error'; message: string; code?: ApiErrorCode }
  | { status: 'done'; result: SimulationResponse };

interface SimulationPageProps {
  personaId: number;
  onNavigateToPersonas?: () => void;
}

export function SimulationPage({
  personaId,
  onNavigateToPersonas,
}: SimulationPageProps) {
  const [query, setQuery] = useState('');
  const [state, setState] = useState<RunState>({ status: 'idle' });
  const [slowPhase, setSlowPhase] = useState<SlowRequestPhase | null>(null);
  // 결과 컴포넌트 안에서 부르면 결과가 뜬 뒤에야 조회가 시작돼 코드가
  // 라벨로 바뀌는 깜빡임이 보인다. 화면에 들어오는 순간 받아둔다.
  const categoryLabel = useCategoryLabels();

  const run = useCallback(
    (trimmed: string) => {
      setState({ status: 'running' });
      setSlowPhase(null);
      runSimulation(personaId, trimmed, { onSlowRequest: setSlowPhase })
        .then((result) => setState({ status: 'done', result }))
        .catch((err: unknown) => {
          if (err instanceof ApiRequestError) {
            setState({ status: 'error', message: err.message, code: err.code });
            return;
          }
          setState({ status: 'error', message: '시뮬레이션을 실행하지 못했습니다.' });
        });
    },
    [personaId],
  );

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = query.trim();
    if (trimmed.length === 0) return;
    run(trimmed);
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
          {slowPhase && (
            <p className="text-xs text-gray-500">{SLOW_REQUEST_MESSAGE[slowPhase]}</p>
          )}
        </div>
      )}

      {state.status === 'error' &&
        (state.code === 'PERSONA_NOT_FOUND' ? (
          <ErrorState
            message={state.message}
            action={<PersonaNotFoundAction onNavigateToPersonas={onNavigateToPersonas} />}
          />
        ) : (
          // 재시도는 마지막 질의를 그대로 다시 보낸다. 입력창을 다시 누르게
          // 하면 콜드스타트로 실패했을 때 이용자가 같은 문장을 또 타이핑해야 한다.
          <ErrorState message={state.message} onRetry={() => run(query.trim())} />
        ))}

      {state.status === 'done' && (
        <SimulationResult result={state.result} categoryLabel={categoryLabel} />
      )}
    </section>
  );
}

/**
 * 적자 전환 안내.
 *
 * 계약상 deadPoint 는 하나뿐이라 가장 이른 시점 하나만 온다. 그 문구를 그대로
 * "빠듯 시나리오에서 …" 로 쓰면, 세 시나리오가 모두 음수인 상황에서도 "빠듯하게
 * 쓸 때만 문제" 로 읽힌다. 실제로 페르소나 2 에 180만원 일시불을 넣으면 여유
 * 시나리오까지 -838,052원이다. 위험을 축소해 전달하는 셈이라, 이 서비스가 막으려는
 * 오판을 화면이 거꾸로 유도하게 된다.
 *
 * 값을 새로 계산하지 않는다. 백엔드가 준 balance 의 부호를 세기만 한다.
 */
function DeadPointNotice({
  deadPoint,
  scenarios,
}: {
  deadPoint: DeadPoint;
  scenarios: Scenario[];
}) {
  const negatives = scenarios.filter((s) =>
    s.points.some((p) => p.month === deadPoint.month && p.balance < 0),
  ).length;
  const allNegative = negatives === scenarios.length;

  return (
    <div className="bg-red-50 rounded-xl border border-red-200 p-6">
      <p className="text-sm text-red-600">
        <span className="font-semibold">
          {allNegative
            ? `어떤 경우에도 ${deadPoint.month} 잔고가 마이너스로 전환됩니다.`
            : `${SCENARIO_LABEL[deadPoint.level]} 시나리오에서 ${deadPoint.month} 잔고가 마이너스로 전환됩니다.`}
        </span>{' '}
        <span className="tabular-nums">{formatWon(deadPoint.shortage)}</span>
        {allNegative ? ' 이상 부족합니다.' : ' 부족합니다.'}
      </p>
    </div>
  );
}

function SimulationResult({
  result,
  categoryLabel,
}: {
  result: SimulationResponse;
  categoryLabel: (code: string) => string;
}) {
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
        {/* 이름표는 GET /api/categories 가 내려준다. 화면에서 지어내면
            마스터와 어긋나므로 대응표를 두지 않는다. 목록을 못 받아오면
            코드를 그대로 보여준다. */}
        <p className="text-xs text-gray-500 mt-1">분류 {categoryLabel(parsed.category)}</p>
      </div>

      {deadPoint !== null ? (
        <DeadPointNotice deadPoint={deadPoint} scenarios={scenarios} />
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
