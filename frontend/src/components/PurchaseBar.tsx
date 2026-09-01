import { useState, type FormEvent } from 'react';

import { MAX_QUERY_LENGTH } from '../api/simulate';

interface PurchaseBarProps {
  running: boolean;
  /** 5초·15초를 넘겼을 때 보여줄 안내. 없으면 그리지 않는다. */
  slowMessage?: string | null;
  onSubmit: (query: string) => void;
}

/**
 * 구매 질문 입력창.
 *
 * 잔고 바로 아래에 둔다. 얼마를 쓸 수 있는지 본 그 자리에서 바로 물어보게
 * 하려는 것이고, 아래에 지난 질문이 쌓이면 채팅하듯 이어 묻는 흐름이 된다.
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
    // 보낸 뒤에는 비운다. 채팅처럼 이어 물을 수 있어야 하고, 남아 있으면
    // 같은 질문을 실수로 두 번 보내기 쉽다.
    setQuery('');
  };

  return (
    <form onSubmit={submit}>
      <div>
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
      </div>
    </form>
  );
}
