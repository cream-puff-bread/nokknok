import { useCallback, useEffect, useState } from 'react';

import { fetchSpending } from '../api/spending';
import {
  ApiRequestError,
  SLOW_REQUEST_MESSAGE,
  type SlowRequestPhase,
} from '../api/client';
import { EmptyState } from './EmptyState';
import { ErrorState } from './ErrorState';
import { PersonaNotFoundAction } from './PersonaNotFoundAction';
import { Skeleton } from './Skeleton';
import {
  formatDate,
  formatWon,
  type ApiErrorCode,
  type SpendingCategory,
  type SpendingSummary,
} from '../types/contract';

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string; code?: ApiErrorCode }
  | { status: 'loaded'; summary: SpendingSummary };

interface SpendingSectionProps {
  personaId: number;
  onNavigateToPersonas?: () => void;
}

/**
 * 한 달 동안 무엇에 얼마를 썼는지.
 *
 * 나머지 화면이 전부 "앞으로 어떻게 될지" 를 말한다. 예측이 이 거래에서
 * 나오므로 이 섹션은 그 근거를 되짚는 자리이기도 하다(contracts/api-spec.yaml
 * /api/spending 설명).
 *
 * CardsSection 과 같이 자기 데이터는 스스로 불러온다 — 상위가 조립만 하고
 * 조회까지 떠맡지 않는다.
 */
export function SpendingSection({ personaId, onNavigateToPersonas }: SpendingSectionProps) {
  const [state, setState] = useState<LoadState>({ status: 'loading' });
  const [slowPhase, setSlowPhase] = useState<SlowRequestPhase | null>(null);

  const load = useCallback(() => {
    setState({ status: 'loading' });
    setSlowPhase(null);
    // month 를 넘기지 않는다. 서버가 거래가 있는 마지막 달을 고른다 —
    // 화면이 "지난달" 로 직접 계산하면 날이 갈수록 빈 달을 가리킨다.
    fetchSpending(personaId, undefined, { onSlowRequest: setSlowPhase })
      .then((summary) => {
        setState({ status: 'loaded', summary });
      })
      .catch((err: unknown) => {
        if (err instanceof ApiRequestError) {
          setState({ status: 'error', message: err.message, code: err.code });
          return;
        }
        setState({ status: 'error', message: '소비 내역을 불러오지 못했습니다.' });
      });
  }, [personaId]);

  useEffect(load, [load]);

  return (
    <section className="space-y-4">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h3 className="text-lg font-semibold text-gray-900 mb-1">무엇에 썼나</h3>
          <p className="text-sm text-gray-500">
            {state.status === 'loaded'
              ? periodCaption(state.summary)
              : '예측이 이 소비에서 나옵니다.'}
          </p>
        </div>
        {state.status === 'loaded' && state.summary.count > 0 && (
          <div className="shrink-0 text-right">
            <p className="text-2xl font-bold tabular-nums text-gray-900">
              {formatWon(state.summary.total)}
            </p>
            <p className="text-xs text-gray-500">{state.summary.count}건</p>
          </div>
        )}
      </div>

      {state.status === 'loading' && (
        <div className="space-y-3">
          {slowPhase && <p className="text-xs text-gray-500">{SLOW_REQUEST_MESSAGE[slowPhase]}</p>}
          <Skeleton className="h-64 w-full rounded-xl" />
        </div>
      )}

      {state.status === 'error' &&
        (state.code === 'PERSONA_NOT_FOUND' ? (
          <ErrorState
            message={state.message}
            action={<PersonaNotFoundAction onNavigateToPersonas={onNavigateToPersonas} />}
          />
        ) : (
          <ErrorState message={state.message} onRetry={load} />
        ))}

      {state.status === 'loaded' &&
        (state.summary.categories.length === 0 ? (
          // 거래가 없는 달은 오류가 아니라 사실이다. monthEnd 도 null 로 온다.
          <EmptyState message="이 기간에는 사용한 내역이 없습니다." />
        ) : (
          // 한 줄에 하나씩 쌓으면 여덟 칸이 세로로 700px 을 먹어 대시보드가
          // 통째로 길어진다. 확정 지출이 높이를 묶어 둔 것과 같은 이유인데,
          // 분포는 한눈에 견줘야 뜻이 생기므로 굴리는 대신 두 칸으로 접는다.
          <ul className="grid gap-x-8 sm:grid-cols-2 bg-white rounded-xl border border-gray-200 p-2">
            {state.summary.categories.map((row) => (
              <CategoryRow key={row.category} row={row} total={state.summary.total} />
            ))}
          </ul>
        ))}
    </section>
  );
}

/**
 * 막대 길이는 합계 대비 비중이다. 최댓값 대비로 그리면 1위가 늘 꽉 찬 막대가
 * 되어 "이 카테고리에 다 썼다" 로 읽히고, 옆에 적힌 % 와도 길이가 어긋난다.
 */
function CategoryRow({ row, total }: { row: SpendingCategory; total: number }) {
  const share = total > 0 ? row.amount / total : 0;

  return (
    <li className="px-4 py-3">
      <div className="flex items-baseline justify-between gap-4 mb-2">
        <span className="text-sm text-gray-900 truncate">{row.categoryLabel}</span>
        <span className="shrink-0 text-sm tabular-nums text-gray-900">
          {formatWon(row.amount)}
          <span className="ml-2 text-xs text-gray-500">{row.count}건</span>
        </span>
      </div>
      <div className="flex items-center gap-3">
        <div className="h-2 flex-1 rounded-full bg-gray-100">
          <div
            className="h-full rounded-full bg-blue-500"
            // 비중이 1% 아래여도 막대가 사라지지는 않게 한다. 0 원이 아니라
            // 적게 쓴 것이므로 "없음" 으로 보이면 안 된다.
            style={{ width: `${Math.max(share * 100, 1.5)}%` }}
          />
        </div>
        <span className="w-10 shrink-0 text-right text-xs tabular-nums text-gray-500">
          {Math.round(share * 100)}%
        </span>
      </div>
    </li>
  );
}

/**
 * 'YYYY-MM' 과 마지막 거래일로 집계 구간을 적는다.
 *
 * monthEnd 를 함께 적는 이유는 계약에 적힌 그대로다 — 20일까지만 거래가 있는
 * 달을 완결된 달처럼 보여주면 합계가 왜 적은지 화면에서 설명할 수 없다.
 * 말일까지 찬 달이면 굳이 덧붙이지 않는다.
 */
function periodCaption(summary: SpendingSummary): string {
  const [year, month] = summary.month.split('-');
  const title = `${year}년 ${Number(month)}월`;
  if (summary.monthEnd === null) return title;

  const lastDay = new Date(Number(year), Number(month), 0).getDate();
  const counted = Number(summary.monthEnd.slice(-2));
  if (counted >= lastDay) return title;
  return `${title} · 1일~${formatDate(summary.monthEnd).split(' ')[1]}까지 집계`;
}
