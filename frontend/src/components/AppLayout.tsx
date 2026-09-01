import { useEffect, useState, type ReactNode } from 'react';
import { Link, useNavigate } from 'react-router';

import { loadPersonasOnce } from '../api/personas';
import type { Persona } from '../types/contract';

interface AppLayoutProps {
  /**
   * personaId가 있는 화면(가용잔고/시뮬레이션/결제 라우팅)에서만 탭을 보여준다.
   * 페르소나 선택·업로드처럼 특정 페르소나에 종속되지 않는 화면은 undefined로 둔다.
   */
  personaId?: number;
  children: ReactNode;
}

/**
 * 사례 전환. 계정 전환처럼 헤더 오른쪽에 둔다.
 *
 * 전에는 "페르소나 선택" 이 착륙 화면이었다. 가상 인물 셋을 늘어놓고 고르게
 * 하면 아무 설명이 나오기 전에 "이건 데모입니다" 라고 말하는 셈이다. 서비스는
 * 이용자가 자기가 누구인지 고르게 하지 않는다.
 *
 * 그래서 전환 자체를 없애지는 않되(사례가 셋인 건 우리 강점이다) 흐름의
 * 중심에서 내린다. 목록을 못 받아오면 아무것도 그리지 않는다 — 이 컨트롤이
 * 없다고 화면이 막히지는 않는다.
 */
function PersonaSwitcher({ personaId }: { personaId: number }) {
  const [personas, setPersonas] = useState<Persona[]>([]);
  const navigate = useNavigate();

  useEffect(() => {
    let alive = true;
    loadPersonasOnce()
      .then((rows) => {
        if (alive) setPersonas(rows);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);

  if (personas.length === 0) return null;

  return (
    <label className="flex items-center gap-2">
      <span className="sr-only">사례 선택</span>
      <select
        value={personaId}
        onChange={(e) => navigate(`/balance/${e.target.value}`)}
        className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-900 focus:border-blue-600 focus:ring-1 focus:ring-blue-600 outline-none"
      >
        {personas.map((p) => (
          <option key={p.id} value={p.id}>
            {p.displayName}
          </option>
        ))}
      </select>
    </label>
  );
}

export function AppLayout({ personaId, children }: AppLayoutProps) {
  // 서비스명은 현재 보고 있는 사례의 대시보드로 돌아간다. 사례 밖 화면
  // (업로드 등)에서는 갈 곳이 정해지지 않으므로 사례 목록으로 보낸다.
  const home = personaId !== undefined ? `/balance/${personaId}` : '/personas';

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b border-gray-200 bg-white">
        <div className="max-w-5xl mx-auto px-4 md:px-8 py-4 flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <Link
                to={home}
                className="text-2xl font-bold text-gray-900 hover:text-blue-600 transition-colors"
              >
                넉넉
              </Link>
              {/* 가상 재무 데이터를 아무 표시 없이 실제 계좌처럼 보여주지 않는다.
                  카드에 "시연용" 뱃지를 붙이는 것과 같은 이유다
                  (schema.sql: 화면에도 명시해야 한다). */}
              <span className="inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium bg-gray-100 text-gray-500">
                시연 데이터
              </span>
            </div>
            {/* 나머지 화면 문구는 "~합니다" 인데 여기만 문서 말투("제시한다")
                였다. 이용자에게 보이는 첫 문장이라 말투를 맞춘다. */}
            <p className="text-sm text-gray-500">
              이미 나갈 돈을 뺀 진짜 쓸 수 있는 잔고와, 어느 카드로 결제할지 계산해 드립니다
            </p>
          </div>

          <div className="flex items-center gap-3">
            {/* 업로드는 사례 선택 화면 하단에 있었는데, 그 화면이 흐름에서
                빠지면서 갈 길이 없어졌다. 시연 데이터가 아니라 자기 명세서로
                돌려볼 수 있다는 건 이 서비스의 설득력 중 하나라 남긴다. */}
            <Link
              to="/upload"
              className="shrink-0 text-xs text-gray-500 underline hover:text-gray-700"
            >
              내 명세서로 해보기
            </Link>
            {personaId !== undefined && <PersonaSwitcher personaId={personaId} />}
          </div>
        </div>

      </header>

      <main className="max-w-5xl mx-auto px-4 md:px-8 py-8">{children}</main>
    </div>
  );
}
