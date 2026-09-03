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
 * 첫 번째 금액은 200만원으로 맞춰 뒀다. 180만원이면 적자가 가장 빠듯한
 * 시나리오에서만 나서 보통 시나리오는 20,030원으로 아슬하게 버티는데, 그
 * 값은 세로축에서 0원과 구별이 안 돼 굵은 선이 0원에 붙은 것처럼 보인다.
 *
 * 200만원이면 결제 방식 셋이 뚜렷하게 갈린다 — 일시불은 세 시나리오가 모두
 * 1개월에 적자, 무이자 3개월은 보통 시나리오가 3개월에 적자, 무이자 6개월은
 * 보통이 32만원을 유지하고 빠듯만 적자다. 경고(빨강)와 주의(호박)가 한
 * 화면에서 다 나오므로 혼자 둘러보는 사람도 토글이 무엇을 바꾸는지 본다.
 */
const SUGGESTIONS = [
  '아이폰 200만원 일시불로 사도 될까?',
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
    // 질문을 카드 안에 담는다. 잔고 카드와 나란히 놓이면 "여기에 물어보는
    // 자리" 라는 게 배치만으로 드러난다.
    <form onSubmit={submit} className="rounded-2xl border border-gray-200 bg-white p-6">
      <div>
        <div className="mb-4 flex items-center gap-2">
          <span
            aria-hidden
            className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-50 text-blue-600"
          >
            <svg viewBox="0 0 24 24" className="h-4 w-4" fill="currentColor">
              <path d="M12 2l1.9 5.7L19.6 9l-5.7 1.9L12 16.6l-1.9-5.7L4.4 9l5.7-1.3L12 2z" />
              <path d="M18.5 14l.9 2.6 2.6.9-2.6.9-.9 2.6-.9-2.6-2.6-.9 2.6-.9.9-2.6z" />
            </svg>
          </span>
          <h3 className="text-base font-semibold text-gray-900">이 결제, 해도 될까요?</h3>
        </div>

        {/* 보내기 버튼을 입력란 안에 넣는다. 입력과 실행이 한 덩어리로 읽히고,
            좁은 화면에서 버튼이 아래로 떨어지지 않는다. */}
        <div className="relative">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            disabled={running}
            maxLength={MAX_QUERY_LENGTH}
            placeholder="예: 아이폰 200만원 할부로 사도 될까?"
            aria-label="사려는 것을 그대로 입력"
            className="w-full rounded-xl bg-gray-100 py-3 pl-4 pr-14 text-sm text-gray-900 outline-none transition-all focus:ring-2 focus:ring-blue-600 disabled:text-gray-400"
          />
          <button
            type="submit"
            disabled={running || query.trim().length === 0}
            aria-label={running ? '계산 중' : '계산하기'}
            className="absolute right-2 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full bg-blue-600 text-white transition-colors hover:bg-blue-700 active:bg-blue-800 disabled:bg-gray-300"
          >
            <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 19V5M5 12l7-7 7 7" />
            </svg>
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
