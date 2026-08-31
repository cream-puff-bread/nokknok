import type { ReactNode } from 'react';
import { NavLink } from 'react-router';

interface AppLayoutProps {
  /**
   * personaId가 있는 화면(가용잔고/시뮬레이션/결제 라우팅)에서만 탭을 보여준다.
   * 페르소나 선택·업로드처럼 특정 페르소나에 종속되지 않는 화면은 undefined로 둔다.
   */
  personaId?: number;
  children: ReactNode;
}

interface TabDef {
  key: string;
  label: string;
  to: (personaId: number) => string;
}

const TABS: TabDef[] = [
  { key: 'balance', label: '가용잔고', to: (id) => `/balance/${id}` },
  { key: 'simulate', label: '시뮬레이션', to: (id) => `/simulate/${id}` },
  { key: 'route', label: '결제 라우팅', to: (id) => `/route/${id}` },
];

export function AppLayout({ personaId, children }: AppLayoutProps) {
  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b border-gray-200 bg-white">
        <div className="max-w-5xl mx-auto px-4 md:px-8 py-4">
          <h1 className="text-2xl font-bold text-gray-900">넉넉</h1>
          <p className="text-sm text-gray-500">
            지출이 확정된 금액을 제외한 가용잔고와 결제 시점을 계산해 제시한다
          </p>
        </div>

        {personaId !== undefined && (
          <nav
            aria-label="화면 전환"
            className="max-w-5xl mx-auto px-4 md:px-8 flex gap-4 overflow-x-auto"
          >
            {TABS.map((tab) => (
              <NavLink
                key={tab.key}
                to={tab.to(personaId)}
                className={({ isActive }) =>
                  `shrink-0 border-b-2 py-3 text-sm font-medium transition-colors ${
                    isActive
                      ? 'border-blue-600 text-blue-600'
                      : 'border-transparent text-gray-500 hover:text-gray-900'
                  }`
                }
              >
                {tab.label}
              </NavLink>
            ))}
          </nav>
        )}
      </header>

      <main className="max-w-5xl mx-auto px-4 md:px-8 py-8">{children}</main>
    </div>
  );
}
