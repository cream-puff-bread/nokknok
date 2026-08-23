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
        {/* 각자 담당 화면은 src/pages/ 에 만들어 여기에 붙인다.
            화면이 여러 개로 늘어날 때 라우팅을 어떻게 할지(react-router 도입 여부)는
            아직 정하지 않았다. 먼저 붙이는 사람이 정하지 말고 팀에 알린다. */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-1">화면 작업 준비 완료</h2>
          <p className="text-sm text-gray-500">
            타입은 <code>src/types/contract.ts</code>, 스타일은{' '}
            <code>contracts/ui-system.md</code> 를 따른다.
          </p>
        </div>
      </main>
    </div>
  );
}
