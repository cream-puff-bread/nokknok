import { useState, type FormEvent } from 'react';

import { MAX_QUERY_LENGTH } from '../api/simulate';

interface PurchaseBarProps {
  running: boolean;
  /** 5초·15초를 넘겼을 때 보여줄 안내. 없으면 그리지 않는다. */
  slowMessage?: string | null;
  onSubmit: (query: string) => void;
}

/**
 * 화면 아래에 고정된 구매 입력 바.
 *
 * 시뮬레이션을 하려고 탭을 눌러 빈 화면으로 가야 했다. 잔고와 카드를 보고
 * 있는 그 자리에서 바로 물어볼 수 있어야 흐름이 끊기지 않는다.
 *
 * 검색창처럼 생긴 것은 즉답을 약속한다. 그런데 질의 해석에 LLM 이 걸려 있어
 * 2초 남짓 걸리고, 서버가 잠들어 있으면 40초까지 간다. 그래서 진행 상태를
 * 바 안에서 그린다 — 입력란 자리에 안내 문구가 뜨고 버튼이 잠긴다. 바깥
 * 어딘가에 스피너를 두면 방금 누른 곳과 반응하는 곳이 달라 멈춘 것처럼 보인다.
 */
export function PurchaseBar({ running, slowMessage, onSubmit }: PurchaseBarProps) {
  const [query, setQuery] = useState('');

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = query.trim();
    if (trimmed.length === 0 || running) return;
    onSubmit(trimmed);
  };

  return (
    // 바깥은 전체 너비로 깔고 안쪽만 본문 폭에 맞춘다. 고정 요소에 max-width 만
    // 주면 흰 바가 가운데만 차지하고 양옆으로 배경이 비친다.
    <div className="fixed inset-x-0 bottom-0 z-40 border-t border-gray-200 bg-white shadow-[0_-8px_32px_rgba(0,0,0,0.06)]">
      <form onSubmit={submit} className="max-w-5xl mx-auto px-4 md:px-8 py-3">
        <div className="flex gap-2">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            disabled={running}
            maxLength={MAX_QUERY_LENGTH}
            placeholder="아이폰 180만원 6개월 할부로 사도 될까?"
            aria-label="사려는 것을 그대로 입력"
            className="flex-1 rounded-xl bg-gray-100 px-4 py-3 text-sm text-gray-900 outline-none transition-all focus:ring-2 focus:ring-blue-600 disabled:text-gray-400"
          />
          <button
            type="submit"
            disabled={running || query.trim().length === 0}
            className="shrink-0 rounded-xl bg-blue-600 px-6 py-3 text-sm font-medium text-white transition-colors hover:bg-blue-700 active:bg-blue-800 disabled:bg-gray-300"
          >
            {running ? '계산 중…' : '계산하기'}
          </button>
        </div>
        {running && (
          <p className="mt-2 text-xs text-gray-500">
            {slowMessage ?? '질의를 해석하고 카드와 잔고를 함께 계산합니다.'}
          </p>
        )}
      </form>
    </div>
  );
}
