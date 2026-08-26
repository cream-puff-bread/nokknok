import { Route, Routes } from 'react-router';

import { routes } from './routes';

export default function App() {
  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b border-gray-200 bg-white">
        <div className="max-w-5xl mx-auto px-4 md:px-8 py-4">
          <h1 className="text-2xl font-bold text-gray-900">넉넉</h1>
          <p className="text-sm text-gray-500">
            지출이 확정된 금액을 제외한 가용잔고와 결제 시점을 계산해 제시한다
          </p>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 md:px-8 py-8">
        {/* 화면을 새로 추가할 때는 src/routes.tsx 의 routes 배열 맨 끝에
            한 줄만 추가한다. 이 파일은 건드릴 필요 없다. */}
        <Routes>
          {routes.map(({ path, element }) => (
            <Route key={path} path={path} element={element} />
          ))}
        </Routes>
      </main>
    </div>
  );
}
