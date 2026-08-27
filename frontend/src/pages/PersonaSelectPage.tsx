import { useCallback, useEffect, useState } from 'react';

import { ApiRequestError, SLOW_REQUEST_MESSAGE, type SlowRequestPhase } from '../api/client';
import { fetchPersonas } from '../api/personas';
import { EmptyState } from '../components/EmptyState';
import { ErrorState } from '../components/ErrorState';
import { PersonaNotFoundAction } from '../components/PersonaNotFoundAction';
import { Skeleton } from '../components/Skeleton';
import { formatWon, type ApiErrorCode, type Persona } from '../types/contract';

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string; code: ApiErrorCode }
  | { status: 'loaded'; personas: Persona[] };

interface PersonaSelectPageProps {
  /**
   * 선택 완료 시 호출된다. 다음 화면으로 어떻게 넘어갈지(라우팅)는 아직
   * 팀에서 정하지 않았으므로(frontend/README.md 미결 사항) 이 컴포넌트는
   * 라우팅을 모른다 — 선택된 Persona만 위로 알린다.
   */
  onSelect?: (persona: Persona) => void;
  /**
   * PERSONA_NOT_FOUND 시 "페르소나 선택으로" 버튼을 눌렀을 때 호출된다.
   * 이 컴포넌트는 라우팅을 모르므로(위 onSelect와 같은 이유) routes.tsx의
   * 래퍼가 useNavigate로 채워준다. PersonaNotFoundAction 참고.
   */
  onNavigateToPersonas?: () => void;
}

export function PersonaSelectPage({ onSelect, onNavigateToPersonas }: PersonaSelectPageProps) {
  const [state, setState] = useState<LoadState>({ status: 'loading' });
  const [selectedId, setSelectedId] = useState<number | null>(null);
  // 콜드스타트 안내 문구. client.ts가 5초·15초 문턱에서 onSlowRequest로
  // 이 값을 갱신해준다 — client.ts는 React를 모르고, 여기서만 state로 받는다.
  const [slowPhase, setSlowPhase] = useState<SlowRequestPhase | null>(null);

  const load = useCallback(() => {
    setState({ status: 'loading' });
    setSlowPhase(null);
    fetchPersonas({ onSlowRequest: setSlowPhase })
      .then((personas) => setState({ status: 'loaded', personas }))
      .catch((err: unknown) => {
        const { message, code } =
          err instanceof ApiRequestError
            ? err
            : { message: '페르소나 목록을 불러오지 못했습니다.', code: 'INTERNAL_ERROR' as const };
        setState({ status: 'error', message, code });
      })
      .finally(() => setSlowPhase(null));
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

      {state.status === 'loading' && (
        <>
          {slowPhase && <p className="text-sm text-gray-500">{SLOW_REQUEST_MESSAGE[slowPhase]}</p>}
          <PersonaSkeletonGrid />
        </>
      )}

      {/* GET /api/personas(목록 조회)는 personaId를 받지 않으므로 계약상
          PERSONA_NOT_FOUND를 내지 않는다. 그래도 code로 분기하는 걸 원칙으로
          맞춰둔다 — 이 페이지가 앞으로 특정 persona를 조회하게 되거나,
          다른 화면이 같은 패턴을 복사해 쓸 때 참고가 되도록. */}
      {state.status === 'error' && (
        state.code === 'PERSONA_NOT_FOUND' ? (
          <ErrorState
            message={state.message}
            action={<PersonaNotFoundAction onNavigateToPersonas={onNavigateToPersonas} />}
          />
        ) : (
          <ErrorState message={state.message} onRetry={load} />
        )
      )}

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
