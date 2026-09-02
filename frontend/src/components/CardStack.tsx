import { useRef, useState, type KeyboardEvent } from 'react';

import { formatWon, type OwnedCard } from '../types/contract';

/**
 * 카드 면 색. 카드에 색 정보가 없으므로 보유 순서로 배정한다.
 *
 * 어두운 색만 쓰는 이유는 ui-system.md 가 초록=성공, 호박=주의로 의미를
 * 배정해 뒀기 때문이다. 카드 면에 그 색을 쓰면 "이 카드가 좋다/나쁘다" 로
 * 잘못 읽힌다. 카드 색은 신원 표시일 뿐이라 의미를 담지 않는다.
 */
const CARD_FACES = [
  'from-slate-800 to-slate-600',
  'from-blue-800 to-blue-600',
  'from-violet-800 to-violet-600',
  'from-amber-700 to-amber-500',
];

/** 겹쳐 쌓을 때 카드 사이 간격. 위 카드의 이름줄이 보일 만큼만 남긴다. */
const STACK_GAP = 76;
/** 마우스를 올린 카드 아래를 벌려 그 카드 전체가 보이게 한다. */
const HOVER_GAP = 176;

interface CardStackProps {
  cards: OwnedCard[];
  onSelect: (card: OwnedCard) => void;
}

/**
 * 지갑에 겹쳐 넣은 것처럼 쌓는 카드 덱.
 *
 * 가로로 늘어놓으면 화면을 넓게 먹는데, 잔고와 질문을 왼쪽에 두고 카드를
 * 오른쪽에 세우려면 좁은 폭에서도 네 장이 한눈에 들어와야 한다. 위 카드의
 * 이름줄만 남기고 겹치면 그 폭에서도 전부 보인다.
 *
 * 마우스를 올리면 그 카드 아래를 벌려 실적까지 보여주고, 누르면 혜택 구간과
 * 제외 항목이 열린다. 훑어보는 것과 자세히 보는 것을 나눈다.
 */
export function CardStack({ cards, onSelect }: CardStackProps) {
  const [hovered, setHovered] = useState<number | null>(null);
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  const offsetOf = (index: number) =>
    // 마우스를 올린 카드보다 아래에 있는 카드들만 밀어 내린다. 위쪽은
    // 그대로 둬야 방금 올린 카드가 제자리에 머문다.
    index * STACK_GAP + (hovered !== null && index > hovered ? HOVER_GAP - STACK_GAP : 0);

  const height = offsetOf(cards.length - 1) + 176;

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const delta = event.key === 'ArrowDown' ? 1 : event.key === 'ArrowUp' ? -1 : 0;
    if (delta === 0) return;
    event.preventDefault();
    const next = (index + delta + cards.length) % cards.length;
    refs.current[next]?.focus();
    setHovered(next);
  };

  return (
    <div
      className="relative transition-[height] duration-300 motion-reduce:transition-none"
      style={{ height }}
      onMouseLeave={() => setHovered(null)}
    >
      {cards.map((card, i) => {
        const active = card.benefits.some((b) => b.active);
        const remaining = (card.perfNextThreshold ?? 0) - card.perfCurrent;
        const open = hovered === i;

        return (
          <button
            key={card.cardId}
            ref={(el) => {
              refs.current[i] = el;
            }}
            type="button"
            onMouseEnter={() => setHovered(i)}
            onFocus={() => setHovered(i)}
            onKeyDown={(event) => onKeyDown(event, i)}
            onClick={() => onSelect(card)}
            aria-label={`${card.cardName} 자세히 보기`}
            style={{ top: offsetOf(i), zIndex: i }}
            className={`absolute inset-x-0 h-44 rounded-2xl p-5 text-left
              flex flex-col justify-between
              bg-gradient-to-br ${CARD_FACES[i % CARD_FACES.length]} text-white
              transition-[top,box-shadow] duration-300 ease-out motion-reduce:transition-none
              focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-2
              ${open ? 'shadow-2xl' : 'shadow-lg'}`}
          >
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="text-xs text-white/70">{card.issuer}</p>
                <p className="text-base font-semibold leading-snug">{card.cardName}</p>
              </div>
              {/* 지금 열려 있는 최고 혜택. 카드를 고를 근거가 이름 옆에 있어야 한다. */}
              {topBenefit(card) !== null && (
                <span className="shrink-0 rounded-md bg-white/20 px-2 py-0.5 text-xs font-medium">
                  {topBenefit(card)}
                </span>
              )}
            </div>

            {/* 마우스를 올린 카드만 실적을 편다. 넷을 한꺼번에 펴면 숫자가
                넷이라 무엇을 봐야 할지 알기 어렵다. */}
            <div
              className={`transition-opacity duration-200 motion-reduce:transition-none ${
                open ? 'opacity-100' : 'opacity-0'
              }`}
            >
              <p className="text-lg font-bold tabular-nums leading-none">
                {formatWon(card.perfCurrent)}
              </p>
              <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-white/20">
                <div
                  className="h-full rounded-full bg-white/80 transition-[width] duration-500 motion-reduce:transition-none"
                  style={{ width: `${progressRatio(card) * 100}%` }}
                />
              </div>
              <p className="mt-1 text-xs text-white/70">
                {active ? '혜택 적용 중' : `${formatWon(remaining)} 더 쓰면 혜택 시작`}
              </p>
            </div>
          </button>
        );
      })}
    </div>
  );
}

/** 지금 적용 중인 혜택 가운데 할인율이 가장 높은 것. 없으면 null. */
function topBenefit(card: OwnedCard): string | null {
  const active = card.benefits.filter((b) => b.active);
  if (active.length === 0) return null;
  const best = active.reduce((a, b) => (b.discountRate > a.discountRate ? b : a));
  return `${best.categoryLabel} ${(best.discountRate * 100).toFixed(0)}%`;
}

/** 실적을 다음 문턱 대비 비율로. 문턱이 없거나 이미 넘겼으면 100% 로 둔다. */
function progressRatio(card: OwnedCard): number {
  if (card.perfNextThreshold === null || card.perfNextThreshold === 0) return 1;
  return Math.min(1, card.perfCurrent / card.perfNextThreshold);
}
