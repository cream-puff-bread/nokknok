import { useCallback, useEffect, useState } from 'react';

import { ApiRequestError } from '../api/client';
import { fetchPersonas } from '../api/personas';
import { EmptyState } from '../components/EmptyState';
import { ErrorState } from '../components/ErrorState';
import { Skeleton } from '../components/Skeleton';
import { formatWon, type Persona } from '../types/contract';

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'loaded'; personas: Persona[] };

interface PersonaSelectPageProps {
  /**
   * 선택 완료 시 호출된다. 다음 화면으로 어떻게 넘어갈지(라우팅)는 아직
   * 팀에서 정하지 않았으므로(frontend/README.md 미결 사항) 이 컴포넌트는
   * 라우팅을 모른다 — 선택된 Persona만 위로 알린다.
   */
  onSelect?: (persona: Persona) => void;
}

export function PersonaSelectPage({ onSelect }: PersonaSelectPageProps) {
  const [state, setState] = useState<LoadState>({ status: 'loading' });
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const load = useCallback(() => {
    setState({ status: 'loading' });
    fetchPersonas()
      .then((personas) => setState({ status: 'loaded', personas }))
      .catch((err: unknown) => {
        const message =
          err instanceof ApiRequestError
            ? err.message
            : '페르소나 목록을 불러오지 못했습니다.';
        setState({ status: 'error', message });
      });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <section className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-gray-900 mb-1">페르소나 선택</h2>
        <p className="text-sm text-gray-500">
          시연용 가상 이용자 중 하나를 선택하면 그 계좌·카드 데이터로 계산합니다.
        </p>
      </div>

      {state.status === 'loading' && <PersonaSkeletonGrid />}

      {state.status === 'error' && <ErrorState message={state.message} onRetry={load} />}

      {state.status === 'loaded' && state.personas.length === 0 && (
        <EmptyState message="선택할 수 있는 페르소나가 없습니다. 시드 데이터가 적재됐는지 확인해 주세요." />
      )}

      {state.status === 'loaded' && state.personas.length > 0 && (
        <div className="grid gap-4 md:grid-cols-3">
          {state.personas.map((persona) => (
            <PersonaCard
              key={persona.id}
              persona={persona}
              selected={persona.id === selectedId}
              onSelect={() => {
                setSelectedId(persona.id);
                onSelect?.(persona);
              }}
            />
          ))}
        </div>
      )}
    </section>
  );
}

interface PersonaCardProps {
  persona: Persona;
  selected: boolean;
  onSelect: () => void;
}

function PersonaCard({ persona, selected, onSelect }: PersonaCardProps) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={`text-left rounded-xl border p-6 transition-colors ${
        selected
          ? 'border-blue-600 bg-blue-50'
          : 'border-gray-200 bg-white hover:bg-gray-50'
      }`}
    >
      <h3 className="text-lg font-semibold text-gray-900 mb-1">{persona.displayName}</h3>
      <p className="text-sm text-gray-500 mb-4">{persona.description}</p>
      <dl className="space-y-1">
        <div className="flex justify-between text-sm">
          <dt className="text-gray-500">계좌 잔액</dt>
          <dd className="text-gray-900 tabular-nums">{formatWon(persona.accountBalance)}</dd>
        </div>
        <div className="flex justify-between text-sm">
          <dt className="text-gray-500">보유 카드</dt>
          <dd className="text-gray-900 tabular-nums">{persona.cardCount}장</dd>
        </div>
      </dl>
    </button>
  );
}

function PersonaSkeletonGrid() {
  return (
    <div className="grid gap-4 md:grid-cols-3">
      {[0, 1, 2].map((i) => (
        <div key={i} className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
          <Skeleton className="h-5 w-2/3" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-1/2" />
        </div>
      ))}
    </div>
  );
}
