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
 * 카드 바탕. 기본값(bg-gray-900)보다 밝은 톤을 쓴다.
 *
 * 짙은 카드를 세 장 겹쳐 붙이면 경계가 안 보여 한 덩어리처럼 읽힌다. 톤을
 * 올리고, 뒤에서 앞으로 갈수록 밝게 해서 깊이가 보이게 한다. 그리는 순서가
 * 뒤에서 앞이므로 배열도 어두운 것부터 둔다.
 */
const CARD_SURFACES = ['bg-slate-800', 'bg-slate-700', 'bg-slate-600', 'bg-slate-500'];

/**
 * 겹쳐 쌓을 때 카드 사이 간격. 위 카드의 이름줄이 보일 만큼만 남긴다.
 *
 * 카드 이름을 위쪽 슬롯에 두므로 아래 블록이 아니라 위 띠만 보이면 된다.
 */
const STACK_GAP = 72;
/**
 * 마우스를 올린 카드 아래를 벌리는 간격.
 *
 * 카드 높이(208px)보다 넉넉히 작게 둬서 아래 카드가 절반 가까이 걸치게 한다.
 * 완전히 떼어 놓으면 덱에서 한 장이 빠져나온 것처럼 보여 쌓인 느낌이 끊긴다.
 */
const HOVER_GAP = 152;
/**
 * 카드 높이.
 *
 * 칸 너비가 320px 이므로 208px 이면 1.54:1 이 되어 실물 신용카드
 * (85.6 x 53.98mm, 약 1.586:1)에 가깝다. 납작하면 카드로 안 읽힌다.
 */
const CARD_HEIGHT = 208;

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
 * 첫 카드가 맨 아래에서 앞에 오도록 쌓는다. 지갑에서 카드를 부채처럼 펴면
 * 앞장이 아래에 오고 뒷장들이 위로 조금씩 삐져나온다 — 그 모습이다.
 *
 * 그러면 뒤 카드들은 위 띠만 드러나므로 이름을 BankCard 의 위쪽 슬롯(brand)에
 * 넣는다. 원래 자리인 아래쪽 title 에 두면 가려져서 어느 카드인지 알 수 없다.
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

  // 쉴 때 높이로 고정한다. 호버로 벌어진 만큼 아래로 넘치게 두는 것이지
  // 칸을 늘리지 않는다 — 늘리면 아래에 있는 확정 지출이 그때마다 밀려
  // 내려가고, 왼쪽 열과 맞춰 둔 아래 선도 흔들린다.
  const height = (cards.length - 1) * STACK_GAP + CARD_HEIGHT;

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const delta = event.key === 'ArrowDown' ? 1 : event.key === 'ArrowUp' ? -1 : 0;
    if (delta === 0) return;
    event.preventDefault();
    const next = (index + delta + cards.length) % cards.length;
    refs.current[next]?.focus();
    setHovered(next);
  };

  return (
    <div className="relative" style={{ height }} onMouseLeave={() => setHovered(null)}>
      {/* 첫 카드를 맨 아래에 두려면 그리는 순서를 뒤집는다. i 가 클수록
          아래이자 앞이므로, 뒤집은 배열의 마지막(원래 첫 카드)이 앞에 온다. */}
      {[...cards].reverse().map((card, i) => {
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
            style={{ top: offsetOf(i), zIndex: i, height: CARD_HEIGHT }}
            className={`absolute inset-x-0 text-left
              transition-[top,box-shadow] duration-300 ease-out motion-reduce:transition-none
              rounded-3xl focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-2
              ${open ? 'drop-shadow-2xl' : 'drop-shadow-lg'}`}
          >
            <BankCard
              className="h-full rounded-3xl ring-1 ring-black/40"
              surface={CARD_SURFACES[i % CARD_SURFACES.length]}
              accent={CARD_ACCENTS[i % CARD_ACCENTS.length]}
              brand={card.cardName}
              subtitle={card.issuer}
              // 아래 블록은 앞에 선 카드에서만 보인다. 굵게 나오는 자리라
              // 결제일 같은 부수 정보 대신 이번 실적을 둔다.
              title={formatWon(card.perfCurrent)}
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
                <div className="h-1 overflow-hidden rounded-full bg-white/20">
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
