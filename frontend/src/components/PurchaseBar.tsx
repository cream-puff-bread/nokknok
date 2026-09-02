import { useState, type FormEvent } from 'react';

import { MAX_QUERY_LENGTH } from '../api/simulate';

/**
 * 눌러 보는 예시.
 *
 * URL 만 받아 혼자 둘러보는 사람에게는 "무엇을 물어볼 수 있는지" 가 안 보인다.
 * 빈 입력창은 아무것도 알려주지 않고, placeholder 하나로는 이 서비스가 자연어를
 * 어디까지 알아듣는지 드러나지 않는다.
 *
 * 네 문장 모두 실제 파서에 넣어 확인했다 — 금액·결제 방식·카테고리가 의도대로
 * 해석되고 카드 추천과 근거 조항까지 나온다. 문장을 바꿀 때는 다시 확인해야
 * 한다. 파싱이 어긋나는 예시를 눌러 보게 하는 건 없느니만 못하다.
 *
 * 첫 번째는 일부러 큰 금액이다. 잔고가 적자로 도는 경우라야 결제 방식을 바꿔
 * 보는 토글이 의미를 갖는다.
 */
const SUGGESTIONS = [
  '아이폰 180만원 일시불로 사도 될까?',
  '외식 8만원 어느 카드가 유리해?',
  '이마트 장보기 25만원',
  '주유 12만원 어떤 카드가 좋아?',
];

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
        {running ? (
          <p className="mt-2 text-xs text-gray-500">
            {slowMessage ?? '질의를 해석하고 카드와 잔고를 함께 계산합니다.'}
          </p>
        ) : (
          <div className="mt-2 flex flex-wrap gap-2">
            {SUGGESTIONS.map((example) => (
              <button
                key={example}
                type="button"
                onClick={() => onSubmit(example)}
                className="rounded-full border border-gray-200 bg-white px-3 py-1.5 text-xs text-gray-500 transition-colors hover:border-gray-300 hover:text-gray-900"
              >
                {example}
              </button>
            ))}
          </div>
        )}
      </div>
    </form>
  );
}
