import { useCallback, useEffect, useState, type FormEvent } from 'react';

import { fetchCategories } from '../api/categories';
import {
  ApiRequestError,
  SLOW_REQUEST_MESSAGE,
  type SlowRequestPhase,
} from '../api/client';
import { runRoute } from '../api/route';
import { runSimulationForPurchase } from '../api/simulate';
import { Button } from '../components/Button';
import { ClauseList } from '../components/ClauseList';
import { DemoBadge, RouteCandidateCard } from '../components/RouteCandidateCard';
import { ErrorState } from '../components/ErrorState';
import { PersonaNotFoundAction } from '../components/PersonaNotFoundAction';
import { Skeleton } from '../components/Skeleton';
import {
  formatWon,
  formatWon as formatWonAmount,
  SCENARIO_LABEL,
  type ApiErrorCode,
  type DeadPoint,
  type ParsedQuery,
  type RouteResponse,
  type SpendCategory,
} from '../types/contract';

type ForecastState =
  | { status: 'idle' }
  | { status: 'running' }
  | { status: 'done'; deadPoint: DeadPoint | null }
  | { status: 'error'; message: string };

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
  // null=조회 중, []=조회 실패, 목록=성공. []를 초기값으로 두면 "아직 응답
  // 안 옴"과 "조회 실패"가 같은 값이 되어, 응답 오기 전 잠깐 자유 입력
  // <input>이 떴다가 <select>로 바뀌는 순간 사용자가 그새 입력한 문자열이
  // 코드값과 안 맞아 화면 표시("외식")와 실제 전송값("온라인")이 어긋나는
  // 문제가 있었다(하영님 리뷰, 2026-08-31).
  const [categories, setCategories] = useState<SpendCategory[] | null>(null);
  // 잔고 답을 새 페이지로 넘기지 않고 이 자리에서 편다. 페이지가 통째로
  // 바뀌면 방금 본 카드 추천이 화면에서 사라져 두 답을 머릿속에서 합쳐야 한다.
  const [forecast, setForecast] = useState<ForecastState>({ status: 'idle' });
  const [state, setState] = useState<RunState>({ status: 'idle' });
  const [slowPhase, setSlowPhase] = useState<SlowRequestPhase | null>(null);

  // spend_category는 DB 소유 값이라 화면이 지어내면 안 된다(frontend/README.md
  // "카테고리 선택지는 GET /api/categories로 받는다"). 자유 입력으로 두면
  // "온라인"처럼 그럴듯한 한글을 쳐서 INVALID_CATEGORY로 막히는 경우가
  // 실제 시연 점검에서 나왔다(8/31 배포본 점검).
  //
  // 목록 조회가 실패해도 화면을 막지 않는다 — 그러면 결제 라우팅 자체를
  // 아예 못 쓰게 되므로, 이 경우에만 예외적으로 자유 입력을 허용한다.
  useEffect(() => {
    let alive = true;
    fetchCategories()
      .then((result) => {
        if (alive) setCategories(result);
      })
      .catch(() => {
        if (alive) setCategories([]);
      });
    return () => {
      alive = false;
    };
  }, []);

  // 검증을 여기 한 곳에 둔다. submit은 폼 제출이라 자연히 이 검증을
  // 거치지만, onRetry는 오류 화면에서 버튼 하나로 바로 이 함수를
  // 부르므로 여기서 막지 않으면 오류 상태에서 입력을 지운 채 재시도할
  // 때 amount=0 같은 값이 그대로 나가 새 422를 만든다.
  const run = useCallback(
    (amountValue: number, categoryValue: string) => {
      if (!Number.isInteger(amountValue) || amountValue <= 0 || categoryValue.length === 0) {
        return;
      }
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

  const runForecast = useCallback(
    (purchase: ParsedQuery) => {
      setForecast({ status: 'running' });
      runSimulationForPurchase(personaId, purchase)
        .then((result) => setForecast({ status: 'done', deadPoint: result.deadPoint }))
        .catch((err: unknown) => {
          const message =
            err instanceof ApiRequestError ? err.message : '잔고를 계산하지 못했습니다.';
          setForecast({ status: 'error', message });
        });
    },
    [personaId],
  );

  const submit = (event: FormEvent) => {
    event.preventDefault();
    run(Number(amount), category.trim().toUpperCase());
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
            <span className="text-xs text-gray-500 mb-1 block">카테고리</span>
            {categories === null ? (
              // 조회 중. 자유 입력으로 잘못 폴백하면(과거 버그) 그 사이 입력한
              // 문자열이 응답 도착 후 <select>로 바뀔 때 코드값과 안 맞아
              // 화면 표시와 실제 전송값이 어긋난다 — 그래서 조회 완료 전까지는
              // select 자체를 비활성화해 아무 값도 못 고르게 막는다.
              <select
                disabled
                className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm outline-none bg-white text-gray-400"
              >
                <option>불러오는 중…</option>
              </select>
            ) : categories.length > 0 ? (
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                disabled={running}
                className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:border-blue-600 focus:ring-1 focus:ring-blue-600 outline-none bg-white"
              >
                <option value="" disabled>
                  선택하세요
                </option>
                {categories.map((c) => (
                  <option key={c.code} value={c.code}>
                    {c.label}
                  </option>
                ))}
              </select>
            ) : (
              // 목록 조회가 실제로 실패했을 때만(빈 배열 확정) 자유 입력으로
              // 대체한다 — 계산 자체를 아예 못 하게 막는 것보다는 낫다.
              <input
                type="text"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                disabled={running}
                placeholder="예: ONLINE, DINING, TAX"
                className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:border-blue-600 focus:ring-1 focus:ring-blue-600 outline-none"
              />
            )}
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

      {state.status === 'done' && (
        <RouteResult
          result={state.result}
          forecast={forecast}
          onSimulate={() =>
            runForecast({
              amount: amountValue,
              category: category.trim().toUpperCase(),
              // 추천받은 결제 방식을 그대로 넘긴다 — 이용자가 확인한 것이
              // "이 카드로 이렇게 결제" 이므로 잔고도 그 조건으로 그린다.
              paymentType: state.result.best.paymentType,
              installmentMonths: state.result.best.installmentMonths,
            })
          }
        />
      )}
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

function RouteResult({
  result,
  forecast,
  onSimulate,
}: {
  result: RouteResponse;
  forecast: ForecastState;
  onSimulate: () => void;
}) {
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

        {forecast.status === 'idle' && (
          <Button variant="secondary" onClick={onSimulate}>
            이 결제로 6개월 잔고 보기
          </Button>
        )}
        {forecast.status === 'running' && <Skeleton className="h-5 w-64" />}
        {forecast.status === 'error' && (
          <p className="text-sm text-gray-500">{forecast.message}</p>
        )}
        {forecast.status === 'done' &&
          (forecast.deadPoint ? (
            // 할인만 보고 결제하면 놓치는 것을 여기서 잡는다.
            <p className="text-sm text-red-600">
              결제 후{' '}
              <span className="font-semibold">{formatMonth(forecast.deadPoint.month)}</span>{' '}
              잔고가{' '}
              <span className="tabular-nums font-semibold">
                {formatWonAmount(forecast.deadPoint.shortage)}
              </span>{' '}
              부족해집니다
              <span className="text-gray-500">
                {' '}
                ({SCENARIO_LABEL[forecast.deadPoint.level]} 시나리오)
              </span>
            </p>
          ) : (
            <p className="text-sm text-emerald-600">
              결제해도 6개월 안에 잔고가 마이너스로 가지 않습니다
            </p>
          ))}
      </div>

      {newCardSuggestion && (
        <div className="bg-amber-50 rounded-xl border border-amber-200 p-6">
          <p className="text-sm text-amber-600 font-semibold mb-1">
            보유 카드로는 조건을 채우지 못했습니다
          </p>
          <p className="text-sm text-gray-900">
            {newCardSuggestion.cardName} 발급 시 {formatWon(newCardSuggestion.expectedGain)}{' '}
            더 받을 수 있습니다.
            {newCardSuggestion.isDemo && (
              <span className="ml-2">
                <DemoBadge />
              </span>
            )}
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

/** '2026-09' 을 '9월' 로. 차트 축과 표기를 맞춘다(ui-system.md). */
function formatMonth(month: string): string {
  const parsed = Number(month.slice(5, 7));
  return Number.isNaN(parsed) ? month : `${parsed}월`;
}
