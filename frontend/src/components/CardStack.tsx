import { useRef, useState, type KeyboardEvent } from 'react';

import { BankCard } from './BankCard';
import { formatWon, type OwnedCard } from '../types/contract';

/**
 * 카드 포인트색. 카드에 색 정보가 없으므로 보유 순서로 배정한다.
 *
 * BankCard(#37)는 배경이 늘 어두운 유리질이고 이 색은 모서리 글로우로만
 * 쓰인다. 그래도 찬 계열만 고른 이유는 ui-system.md 가 초록=성공,
 * 호박=주의로 의미를 배정해 뒀기 때문이다 — 카드 면에 그 색이 번지면
 * "이 카드가 좋다/나쁘다" 로 잘못 읽힌다. 카드 색은 신원 표시일 뿐이다.
 */
const CARD_ACCENTS = ['#6366f1', '#0ea5e9', '#a855f7', '#64748b'];

/**
 * 겹쳐 쌓을 때 카드 사이 간격.
 *
 * BankCard(#37)의 아래 블록(IC칩 + 카드 이름 + 결제일)이 90px 남짓이라
 * 그보다 좁게 겹치면 이름이 반쯤 잘려 어느 카드인지 알 수 없다. 처음
 * 76px 로 뒀다가 실제로 잘리는 것을 보고 늘렸다.
 */
const STACK_GAP = 104;
/** 마우스를 올린 카드 아래를 벌려 그 카드 전체가 보이게 한다. */
const HOVER_GAP = 190;

interface CardStackProps {
  cards: OwnedCard[];
  onSelect: (card: OwnedCard) => void;
}

/**
 * 지갑에 겹쳐 넣은 것처럼 쌓는 카드 덱.
 *
 * 가로로 늘어놓으면 화면을 넓게 먹는데, 잔고와 질문을 왼쪽에 두고 카드를
 * 오른쪽에 세우려면 좁은 폭에서도 네 장이 한눈에 들어와야 한다. 겹쳐 쌓고
 * 한 장마다 한 띠씩만 남기면 그 폭에서도 전부 보인다.
 *
 * 위 카드가 앞에 오도록 쌓는다(z-index 역순). BankCard(#37)는 카드 이름을
 * 아래쪽 IC칩 옆에 두므로, 아래 카드의 위쪽을 가리면 이름이 안 보여 어느
 * 카드인지 알 수 없다. 반대로 쌓으면 각 카드의 아래 띠 — 이름이 있는 쪽 —
 * 가 드러난다.
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
            style={{ top: offsetOf(i), zIndex: cards.length - i }}
            className={`absolute inset-x-0 h-44 text-left
              transition-[top,box-shadow] duration-300 ease-out motion-reduce:transition-none
              rounded-2xl focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-2
              ${open ? 'shadow-2xl' : ''}`}
          >
            <BankCard
              className="h-full"
              accent={CARD_ACCENTS[i % CARD_ACCENTS.length]}
              brand={card.issuer}
              title={card.cardName}
              footer={`매월 ${card.paymentDay}일 결제`}
              demoBadge={
                <div className="flex flex-col items-end gap-1">
                  {/* 지금 열려 있는 최고 혜택. 카드를 고를 근거가 면에 있어야 한다. */}
                  {topBenefit(card) !== null && (
                    <span className="rounded-md bg-white/20 px-2 py-0.5 text-xs font-medium text-white">
                      {topBenefit(card)}
                    </span>
                  )}
                  {card.isDemo && (
                    <span className="rounded-md bg-white/10 px-2 py-0.5 text-[10px] font-medium text-white/70">
                      시연용
                    </span>
                  )}
                </div>
              }
            >
              {/* 마우스를 올린 카드만 실적을 편다. 넷을 한꺼번에 펴면 숫자가
                  넷이라 무엇을 봐야 할지 알기 어렵다. */}
              <div
                className={`mt-2 transition-opacity duration-200 motion-reduce:transition-none ${
                  open ? 'opacity-100' : 'opacity-0'
                }`}
              >
                <p className="text-sm font-bold tabular-nums leading-none text-white">
                  {formatWon(card.perfCurrent)}
                </p>
                <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-white/20">
                  <div
                    className="h-full rounded-full bg-white/80 transition-[width] duration-500 motion-reduce:transition-none"
                    style={{ width: `${progressRatio(card) * 100}%` }}
                  />
                </div>
                <p className="mt-1 text-[10px] text-white/60">
                  {active ? '혜택 적용 중' : `${formatWon(remaining)} 더 쓰면 혜택 시작`}
                </p>
              </div>
            </BankCard>
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
