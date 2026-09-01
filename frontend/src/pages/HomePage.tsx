import { useCallback, useEffect, useRef, useState } from 'react';

import { fetchBalance } from '../api/balance';
import { useCategoryLabels } from '../api/categories';
import { runRoute } from '../api/route';
import { runSimulation } from '../api/simulate';
import {
  ApiRequestError,
  SLOW_REQUEST_MESSAGE,
  type SlowRequestPhase,
} from '../api/client';
import { EmptyState } from '../components/EmptyState';
import { BalanceTrendChart } from '../components/BalanceTrendChart';
import { CardsSection } from '../components/CardsSection';
import { PurchaseBar } from '../components/PurchaseBar';
import { Receipt } from '../components/Receipt';
import { ErrorState } from '../components/ErrorState';
import { PersonaNotFoundAction } from '../components/PersonaNotFoundAction';
import { Skeleton } from '../components/Skeleton';
import {
  EXPENSE_TYPE_LABEL,
  formatWon,
  type ApiErrorCode,
  type BalanceResponse,
  type FixedExpense,
  type ParsedQuery,
  type RouteResponse,
  type SimulationResponse,
} from '../types/contract';

/**
 * 입력 한 번으로 두 답을 모은다 — "어느 카드로" 와 "그래서 잔고가 어떻게".
 *
 * 질의 해석이 시뮬레이션 응답에 들어 있어 순서가 정해진다(해석 결과가 있어야
 * 라우팅에 넘길 금액·카테고리를 안다). 그래서 시뮬레이션이 돌아오는 즉시
 * 영수증을 먼저 띄우고 카드 칸만 마저 채운다 — 둘 다 기다리면 4초 넘게
 * 빈 화면을 보게 된다.
 */
type PurchaseState =
  | { status: 'idle' }
  | { status: 'parsing' }
  | {
      status: 'done';
      purchase: ParsedQuery;
      // 데드포인트만 들고 있으면 영수증은 그릴 수 있어도 6개월 추이는 못
      // 그린다. 한 화면에서 답을 끝내려면 시나리오까지 필요하다.
      simulation: SimulationResponse;
      route: RouteResponse | null;
      routeLoading: boolean;
    }
  | { status: 'error'; message: string };

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string; code?: ApiErrorCode }
  | { status: 'loaded'; balance: BalanceResponse };

interface HomePageProps {
  personaId: number;
  onNavigateToPersonas?: () => void;
}

export function HomePage({
  personaId,
  onNavigateToPersonas,
}: HomePageProps) {
  const [state, setState] = useState<LoadState>({ status: 'loading' });
  const [slowPhase, setSlowPhase] = useState<SlowRequestPhase | null>(null);
  const [purchase, setPurchase] = useState<PurchaseState>({ status: 'idle' });
  const [purchaseSlow, setPurchaseSlow] = useState<SlowRequestPhase | null>(null);
  const categoryLabel = useCategoryLabels();
  const receiptRef = useRef<HTMLDivElement | null>(null);

  // 입력은 화면 맨 아래에서 하는데 답은 위에 뜬다. 스크롤을 옮겨 주지 않으면
  // 방금 누른 사람이 아무 일도 안 일어났다고 느낀다.
  useEffect(() => {
    if (purchase.status !== 'done') return;
    receiptRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [purchase.status]);

  const askPurchase = useCallback(
    (query: string) => {
      setPurchase({ status: 'parsing' });
      setPurchaseSlow(null);
      runSimulation(personaId, query, { onSlowRequest: setPurchaseSlow })
        .then((simulation) => {
          setPurchase({
            status: 'done',
            purchase: simulation.parsed,
            simulation,
            route: null,
            routeLoading: true,
          });
          return runRoute(personaId, simulation.parsed.amount, simulation.parsed.category)
            .then((route) =>
              setPurchase((prev) =>
                prev.status === 'done' ? { ...prev, route, routeLoading: false } : prev,
              ),
            )
            // 카드 추천이 실패해도 잔고 답은 이미 화면에 있다. 영수증을
            // 통째로 지우지 않고 그 칸만 비운다.
            .catch(() =>
              setPurchase((prev) =>
                prev.status === 'done' ? { ...prev, routeLoading: false } : prev,
              ),
            );
        })
        .catch((err: unknown) => {
          const message =
            err instanceof ApiRequestError ? err.message : '계산하지 못했습니다.';
          setPurchase({ status: 'error', message });
        });
    },
    [personaId],
  );

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
    // 아래 고정 바가 본문 끝을 가리지 않도록 여백을 둔다.
    <section className="space-y-6 pb-32">
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

      {purchase.status === 'error' && <ErrorState message={purchase.message} />}

      {purchase.status === 'done' && (
        // 답은 잔고 바로 아래에 둔다. 목록 끝에 붙이면 바에 입력한 사람이
        // 한참 아래로 내려가야 답을 본다.
        <div ref={receiptRef} className="scroll-mt-32">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">이 결제, 해도 될까요</h3>
          <Receipt
            purchase={purchase.purchase}
            categoryLabel={categoryLabel}
            route={purchase.route}
            routeLoading={purchase.routeLoading}
            deadPoint={purchase.simulation.deadPoint}
            forecastLoaded
          />

          <div className="mt-4">
            <BalanceTrendChart
              scenarios={purchase.simulation.scenarios}
              deadPoint={purchase.simulation.deadPoint}
            />
          </div>
        </div>
      )}

      <CardsSection personaId={personaId} onNavigateToPersonas={onNavigateToPersonas} />

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

      <PurchaseBar
        running={purchase.status === 'parsing' || (purchase.status === 'done' && purchase.routeLoading)}
        slowMessage={purchaseSlow ? SLOW_REQUEST_MESSAGE[purchaseSlow] : null}
        onSubmit={askPurchase}
      />
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
