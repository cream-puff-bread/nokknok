import { useCallback, useState, type FormEvent } from 'react';

import {
  ApiRequestError,
  SLOW_REQUEST_MESSAGE,
  type SlowRequestPhase,
} from '../api/client';
import { runRoute } from '../api/route';
import { Button } from '../components/Button';
import { ClauseList } from '../components/ClauseList';
import { ErrorState } from '../components/ErrorState';
import { PersonaNotFoundAction } from '../components/PersonaNotFoundAction';
import { RouteCandidateCard } from '../components/RouteCandidateCard';
import { Skeleton } from '../components/Skeleton';
import { formatWon, type ApiErrorCode, type RouteResponse } from '../types/contract';

type RunState =
  | { status: 'idle' }
  | { status: 'running' }
  | { status: 'error'; message: string; code?: ApiErrorCode }
  | { status: 'done'; result: RouteResponse };

interface RouteResultPageProps {
  personaId: number;
  onNavigateToPersonas?: () => void;
}

export function RouteResultPage({ personaId, onNavigateToPersonas }: RouteResultPageProps) {
  const [amount, setAmount] = useState('');
  const [category, setCategory] = useState('');
  const [state, setState] = useState<RunState>({ status: 'idle' });
  const [slowPhase, setSlowPhase] = useState<SlowRequestPhase | null>(null);

  const run = useCallback(
    (amountValue: number, categoryValue: string) => {
      setState({ status: 'running' });
      setSlowPhase(null);
      runRoute(personaId, amountValue, categoryValue, { onSlowRequest: setSlowPhase })
        .then((result) => setState({ status: 'done', result }))
        .catch((err: unknown) => {
          if (err instanceof ApiRequestError) {
            setState({ status: 'error', message: err.message, code: err.code });
            return;
          }
          setState({ status: 'error', message: '결제 라우팅을 계산하지 못했습니다.' });
        });
    },
    [personaId],
  );

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const amountValue = Number(amount);
    const categoryValue = category.trim().toUpperCase();
    if (!Number.isInteger(amountValue) || amountValue <= 0 || categoryValue.length === 0) {
      return;
    }
    run(amountValue, categoryValue);
  };

  const running = state.status === 'running';
  const amountValue = Number(amount);
  const canSubmit =
    !running &&
    Number.isInteger(amountValue) &&
    amountValue > 0 &&
    category.trim().length > 0;

  return (
    <section className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-gray-900 mb-1">결제 라우팅</h3>
        <p className="text-sm text-gray-500">
          결제 금액과 카테고리를 입력하면 보유 카드 중 어느 카드가 유리한지 계산합니다.
        </p>
      </div>

      <form onSubmit={submit} className="space-y-4">
        <div className="flex gap-4">
          <label className="flex-1 block">
            <span className="text-xs text-gray-500 mb-1 block">결제 금액</span>
            <input
              type="number"
              min={1}
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              disabled={running}
              placeholder="100000"
              className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:border-blue-600 focus:ring-1 focus:ring-blue-600 outline-none"
            />
          </label>
          <label className="flex-1 block">
            <span className="text-xs text-gray-500 mb-1 block">카테고리 코드</span>
            <input
              type="text"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              disabled={running}
              placeholder="예: ONLINE, DINING, TAX"
              className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:border-blue-600 focus:ring-1 focus:ring-blue-600 outline-none"
            />
          </label>
        </div>
        <Button type="submit" disabled={!canSubmit}>
          {running ? '계산 중…' : '계산하기'}
        </Button>
      </form>

      {running && (
        <div className="space-y-4">
          <Skeleton className="h-40 w-full rounded-xl" />
          <Skeleton className="h-24 w-full rounded-xl" />
          <p className="text-xs text-gray-500">보유 카드를 비교하는 중입니다.</p>
          {slowPhase && (
            <p className="text-xs text-gray-500">{SLOW_REQUEST_MESSAGE[slowPhase]}</p>
          )}
        </div>
      )}

      {state.status === 'error' && (
        <RouteErrorDisplay
          message={state.message}
          code={state.code}
          onRetry={() => run(amountValue, category.trim().toUpperCase())}
          onNavigateToPersonas={onNavigateToPersonas}
        />
      )}

      {state.status === 'done' && <RouteResult result={state.result} />}
    </section>
  );
}

function RouteErrorDisplay({
  message,
  code,
  onRetry,
  onNavigateToPersonas,
}: {
  message: string;
  code?: ApiErrorCode;
  onRetry: () => void;
  onNavigateToPersonas?: () => void;
}) {
  if (code === 'PERSONA_NOT_FOUND') {
    return (
      <ErrorState
        message={message}
        action={<PersonaNotFoundAction onNavigateToPersonas={onNavigateToPersonas} />}
      />
    );
  }
  // NO_VERIFIED_RULE은 입력을 고쳐도 달라지지 않는 상황이다(contracts/types.ts
  // ApiErrorCode 주석). "다시 시도" 버튼을 주면 똑같은 요청을 또 보내게 되므로
  // 안내 문구만 보여준다.
  if (code === 'NO_VERIFIED_RULE') {
    return <ErrorState message={message} />;
  }
  return <ErrorState message={message} onRetry={onRetry} />;
}

function RouteResult({ result }: { result: RouteResponse }) {
  const { best, alternatives, newCardSuggestion, computeMeta } = result;

  return (
    <div className="space-y-6">
      <div className="space-y-3">
        <RouteCandidateCard candidate={best} highlight />
        {best.explanation ? (
          <p className="text-sm text-gray-900 bg-white rounded-xl border border-gray-200 p-4">
            {best.explanation}
          </p>
        ) : (
          // LLM 생성 실패 시 explanation=null이어도 계산 결과(위 카드)는
          // 이미 표시됐다. 설명만 없다는 걸 알리되 결과를 가리지 않는다.
          <p className="text-xs text-gray-500">
            설명을 생성하지 못했습니다. 계산된 숫자는 그대로 유효합니다.
          </p>
        )}
        <ClauseList clauses={best.clauses} />
      </div>

      {newCardSuggestion && (
        <div className="bg-amber-50 rounded-xl border border-amber-200 p-6">
          <p className="text-sm text-amber-600 font-semibold mb-1">
            보유 카드로는 조건을 채우지 못했습니다
          </p>
          <p className="text-sm text-gray-900">
            {newCardSuggestion.cardName} 발급 시 {formatWon(newCardSuggestion.expectedGain)}{' '}
            더 받을 수 있습니다.
            {newCardSuggestion.isAffiliate && (
              <span className="ml-2 inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium bg-amber-100 text-amber-700">
                제휴
              </span>
            )}
          </p>
        </div>
      )}

      {alternatives.length > 0 && (
        <div className="space-y-3">
          <h4 className="text-sm text-gray-900">다른 카드</h4>
          {alternatives.map((candidate) => (
            <RouteCandidateCard key={candidate.cardId} candidate={candidate} />
          ))}
        </div>
      )}

      {computeMeta.excludedUnverifiedCards > 0 && (
        <p className="text-xs text-gray-500">
          검수가 끝나지 않은 카드 {computeMeta.excludedUnverifiedCards}장은 후보에서 제외했습니다.
        </p>
      )}
    </div>
  );
}
