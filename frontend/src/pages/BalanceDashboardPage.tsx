import { useCallback, useEffect, useState } from 'react';

import { fetchBalance } from '../api/balance';
import {
  ApiRequestError,
  SLOW_REQUEST_MESSAGE,
  type SlowRequestPhase,
} from '../api/client';
import { EmptyState } from '../components/EmptyState';
import { ErrorState } from '../components/ErrorState';
import { PersonaNotFoundAction } from '../components/PersonaNotFoundAction';
import { Skeleton } from '../components/Skeleton';
import {
  EXPENSE_TYPE_LABEL,
  formatWon,
  type ApiErrorCode,
  type BalanceResponse,
  type FixedExpense,
} from '../types/contract';

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string; code?: ApiErrorCode }
  | { status: 'loaded'; balance: BalanceResponse };

interface BalanceDashboardPageProps {
  personaId: number;
  onNavigateToPersonas?: () => void;
}

export function BalanceDashboardPage({
  personaId,
  onNavigateToPersonas,
}: BalanceDashboardPageProps) {
  const [state, setState] = useState<LoadState>({ status: 'loading' });
  const [slowPhase, setSlowPhase] = useState<SlowRequestPhase | null>(null);

  const load = useCallback(() => {
    setState({ status: 'loading' });
    setSlowPhase(null);
    fetchBalance(personaId, { onSlowRequest: setSlowPhase })
      .then((balance) => setState({ status: 'loaded', balance }))
      .catch((err: unknown) => {
        if (err instanceof ApiRequestError) {
          setState({ status: 'error', message: err.message, code: err.code });
          return;
        }
        setState({ status: 'error', message: '가용잔고를 불러오지 못했습니다.' });
      });
  }, [personaId]);

  useEffect(() => {
    load();
  }, [load]);

  if (state.status === 'loading') {
    return (
      <section className="space-y-4">
        <Skeleton className="h-32 w-full rounded-xl" />
        <Skeleton className="h-40 w-full rounded-xl" />
        {slowPhase && (
          <p className="text-xs text-gray-500">{SLOW_REQUEST_MESSAGE[slowPhase]}</p>
        )}
      </section>
    );
  }

  if (state.status === 'error') {
    // 없는 페르소나는 재시도해도 영원히 없다. 이용자가 취해야 할 다음 행동이
    // 다르므로 화면도 달라야 한다(#20 에서 세운 원칙).
    return state.code === 'PERSONA_NOT_FOUND' ? (
      <ErrorState
        message={state.message}
        action={<PersonaNotFoundAction onNavigateToPersonas={onNavigateToPersonas} />}
      />
    ) : (
      <ErrorState message={state.message} onRetry={load} />
    );
  }

  const { accountBalance, fixedTotal, availableBalance, fixedExpenses } = state.balance;

  return (
    <section className="space-y-6">
      <div className="bg-blue-50 rounded-xl border border-blue-200 p-6">
        <p className="text-sm text-gray-500 mb-1">가용잔고</p>
        <p
          className={`text-3xl font-bold tabular-nums ${
            availableBalance < 0 ? 'text-red-600' : 'text-gray-900'
          }`}
        >
          {formatWon(availableBalance)}
        </p>
        <dl className="flex gap-6 mt-4">
          <div>
            <dt className="text-xs text-gray-500 mb-1">통장 잔액</dt>
            <dd className="text-sm text-gray-900 tabular-nums">
              {formatWon(accountBalance)}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-gray-500 mb-1">확정 지출</dt>
            <dd className="text-sm text-gray-900 tabular-nums">
              −{formatWon(fixedTotal)}
            </dd>
          </div>
        </dl>
        {availableBalance < 0 && (
          <p className="text-sm text-red-600 mt-4">
            확정 지출이 통장 잔액을 넘습니다. 이미 자금이 부족한 상태입니다.
          </p>
        )}
      </div>

      <div>
        <h3 className="text-lg font-semibold text-gray-900 mb-1">확정 지출</h3>
        <p className="text-sm text-gray-500 mb-4">
          이미 빠져나갈 금액과 날짜가 정해진 항목입니다.
        </p>
        {fixedExpenses.length === 0 ? (
          <EmptyState message="등록된 확정 지출이 없습니다. 통장 잔액 전부를 쓸 수 있습니다." />
        ) : (
          <ul className="bg-white rounded-xl border border-gray-200 divide-y divide-gray-200">
            {fixedExpenses.map((expense, i) => (
              <FixedExpenseRow key={`${expense.label}-${i}`} expense={expense} />
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

function FixedExpenseRow({ expense }: { expense: FixedExpense }) {
  return (
    <li className="flex items-center justify-between gap-4 p-6">
      <div className="min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className="text-sm text-gray-900 truncate">{expense.label}</span>
          <span className="inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium bg-blue-50 text-blue-600">
            {EXPENSE_TYPE_LABEL[expense.expenseType]}
          </span>
          {expense.unusedSuspect && (
            <span className="inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium bg-amber-50 text-amber-600">
              미사용 의심
            </span>
          )}
        </div>
        <p className="text-xs text-gray-500">매월 {expense.chargeDay}일 청구</p>
      </div>
      <span className="text-sm text-gray-900 tabular-nums shrink-0">
        {formatWon(expense.amount)}
      </span>
    </li>
  );
}
