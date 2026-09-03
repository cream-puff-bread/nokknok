import { useCallback, useEffect, useState } from 'react';

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
import { CardsSection } from '../components/CardsSection';
import { PurchaseBar } from '../components/PurchaseBar';
import { ForecastToggle } from '../components/ForecastToggle';
import { Modal } from '../components/Modal';
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
/**
 * 물어본 것 한 건. 답까지 들고 있어서 기록을 다시 눌러도 계산을 반복하지 않는다.
 *
 * 데드포인트만 들고 있으면 영수증은 그려도 6개월 추이는 못 그리므로
 * 시뮬레이션 응답을 통째로 보관한다.
 */
interface AskEntry {
  id: number;
  query: string;
  purchase: ParsedQuery;
  simulation: SimulationResponse;
  route: RouteResponse | null;
  routeLoading: boolean;
}

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
  // 물어본 것들. 최근 것이 위로 온다. 답은 모달에만 띄우고 여기에는 질문만
  // 남긴다 — 결과를 페이지에도 펼치면 같은 내용이 두 번 있는 것처럼 읽힌다.
  const [history, setHistory] = useState<AskEntry[]>([]);
  const [openId, setOpenId] = useState<number | null>(null);
  const [asking, setAsking] = useState(false);
  const [askError, setAskError] = useState<string | null>(null);
  const [purchaseSlow, setPurchaseSlow] = useState<SlowRequestPhase | null>(null);
  const categoryLabel = useCategoryLabels();

  const open = history.find((entry) => entry.id === openId) ?? null;

  const askPurchase = useCallback(
    (query: string) => {
      const id = Date.now();
      setAsking(true);
      setAskError(null);
      setPurchaseSlow(null);
      const patch = (change: Partial<AskEntry>) =>
        setHistory((prev) => prev.map((e) => (e.id === id ? { ...e, ...change } : e)));

      runSimulation(personaId, query, { onSlowRequest: setPurchaseSlow })
        .then((simulation) => {
          setHistory((prev) => [
            {
              id,
              query,
              purchase: simulation.parsed,
              simulation,
              route: null,
              routeLoading: true,
            },
            ...prev,
          ]);
          setOpenId(id);
          setAsking(false);
          return runRoute(personaId, simulation.parsed.amount, simulation.parsed.category)
            .then((route) => patch({ route, routeLoading: false }))
            // 카드 추천이 실패해도 잔고 답은 이미 모달에 있다. 영수증을
            // 통째로 지우지 않고 그 칸만 비운다.
            .catch(() => patch({ routeLoading: false }));
        })
        .catch((err: unknown) => {
          setAsking(false);
          setAskError(
            err instanceof ApiRequestError ? err.message : '계산하지 못했습니다.',
          );
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
    <section className="space-y-6">
      {/* 잔고와 질문을 왼쪽에, 카드를 오른쪽에 둔다. 세로 한 줄로 쌓으면
          노트북 가로를 절반 넘게 비우게 되고, 심사위원은 노트북으로 본다
          (contracts/ui-system.md). 좁은 화면에서는 한 줄로 돌아간다. */}
      <div className="grid gap-8 md:grid-cols-[minmax(0,1fr)_320px] md:items-start">
        <div className="space-y-6">
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

        <div className="space-y-3">
          <PurchaseBar
            running={asking}
            slowMessage={purchaseSlow ? SLOW_REQUEST_MESSAGE[purchaseSlow] : null}
            onSubmit={askPurchase}
          />

          {askError !== null && <ErrorState message={askError} />}

          {/* 답이 아니라 물어본 것만 남긴다. 결과를 여기에도 펼치면 모달과
              같은 내용이 두 번 있는 것처럼 읽힌다. 누르면 그 때 계산한 답이
              그대로 다시 열린다 — 다시 계산하지 않는다. */}
          {history.length > 0 && (
            <ul className="space-y-1">
              {history.map((entry) => (
                <li key={entry.id}>
                  <button
                    type="button"
                    onClick={() => setOpenId(entry.id)}
                    className="w-full rounded-lg px-3 py-2 text-left text-sm text-gray-500 transition-colors hover:bg-white hover:text-gray-900"
                  >
                    <span className="text-gray-400">↳</span> {entry.query}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <Modal open={open !== null} title="이 결제, 해도 될까요" onClose={() => setOpenId(null)}>
          {open !== null && (
            <ReceiptWithChart
              personaId={personaId}
              purchase={open}
              categoryLabel={categoryLabel}
            />
          )}
        </Modal>
        </div>

        <CardsSection personaId={personaId} onNavigateToPersonas={onNavigateToPersonas} />
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

/** 영수증과 결제 방식별 6개월 추이를 한 덩어리로. */
function ReceiptWithChart({
  personaId,
  purchase,
  categoryLabel,
}: {
  personaId: number;
  purchase: AskEntry;
  categoryLabel: (code: string) => string;
}) {
  return (
    <div className="space-y-6">
      <Receipt
        purchase={purchase.purchase}
        categoryLabel={categoryLabel}
        route={purchase.route}
        routeLoading={purchase.routeLoading}
      />
      <ForecastToggle
        personaId={personaId}
        purchase={purchase.purchase}
        asked={purchase.simulation}
      />
    </div>
  );
}
