import { useRef, type KeyboardEvent } from 'react';

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
];

/** 가운데에서 몇 장 떨어진 카드까지 그릴지. 그 밖은 숨긴다. */
const VISIBLE_DEPTH = 2;

const STEP_X = 210;
const STEP_Z = -160;
const TILT_DEG = 42;

interface CardDeckProps {
  cards: OwnedCard[];
  selectedId: number;
  onSelect: (cardId: number) => void;
}

/**
 * 커버플로우 카드 덱.
 *
 * 카드를 세로로 늘어놓으면 화면이 길어지고 어느 카드를 보는지가 스크롤
 * 위치로만 구분된다. 가운데 한 장을 세우고 나머지를 옆으로 눕히면 "지금
 * 이 카드를 보고 있다" 가 한눈에 들어온다.
 *
 * 정보는 두 단계로 나눈다 — 면에는 카드 신원만 두고, 마우스를 올리면
 * 이번 실적까지, 누르면 아래에 혜택 구간과 제외 항목이 펴진다. 처음부터
 * 다 보여주면 카드가 표가 되어 고를 이유가 사라진다.
 */
export function CardDeck({ cards, selectedId, onSelect }: CardDeckProps) {
  const selectedIndex = Math.max(
    0,
    cards.findIndex((c) => c.cardId === selectedId),
  );
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  // 라디오 그룹은 화살표로 옮길 수 있어야 한다. 커버플로우는 좌우 배치라
  // 좌우 키를 쓴다.
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const delta = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0;
    if (delta === 0) return;
    event.preventDefault();
    const next = (selectedIndex + delta + cards.length) % cards.length;
    onSelect(cards[next].cardId);
    refs.current[next]?.focus();
  };

  return (
    <div
      role="radiogroup"
      aria-label="카드 선택"
      onKeyDown={onKeyDown}
      className="relative h-64 select-none [perspective:1200px]"
    >
      {cards.map((card, i) => {
        const offset = i - selectedIndex;
        const distance = Math.abs(offset);
        const centered = offset === 0;

        return (
          <CardFace
            key={card.cardId}
            ref={(el) => {
              refs.current[i] = el;
            }}
            card={card}
            face={CARD_FACES[i % CARD_FACES.length]}
            centered={centered}
            hidden={distance > VISIBLE_DEPTH}
            style={{
              transform:
                `translate(-50%, -50%)` +
                ` translateX(${offset * STEP_X}px)` +
                ` translateZ(${distance * STEP_Z}px)` +
                ` rotateY(${offset === 0 ? 0 : offset > 0 ? -TILT_DEG : TILT_DEG}deg)`,
              // 가운데에서 멀수록 뒤로 보낸다. 겹칠 때 앞뒤가 뒤집히면
              // 눕힌 카드가 세운 카드를 가린다.
              zIndex: cards.length - distance,
              opacity: distance > VISIBLE_DEPTH ? 0 : centered ? 1 : 0.45,
              pointerEvents: distance > VISIBLE_DEPTH ? 'none' : 'auto',
            }}
            onSelect={() => onSelect(card.cardId)}
          />
        );
      })}
    </div>
  );
}

/** 실적을 다음 문턱 대비 비율로. 문턱이 없거나 이미 넘겼으면 100% 로 둔다. */
function progressRatio(card: OwnedCard): number {
  if (card.perfNextThreshold === null || card.perfNextThreshold === 0) return 1;
  return Math.min(1, card.perfCurrent / card.perfNextThreshold);
}

interface CardFaceProps {
  card: OwnedCard;
  face: string;
  centered: boolean;
  hidden: boolean;
  style: React.CSSProperties;
  onSelect: () => void;
  ref?: (el: HTMLButtonElement | null) => void;
}

function CardFace({ card, face, centered, hidden, style, onSelect, ref }: CardFaceProps) {
  const active = card.benefits.some((b) => b.active);
  const remaining = (card.perfNextThreshold ?? 0) - card.perfCurrent;

  return (
    <button
      ref={ref}
      type="button"
      role="radio"
      aria-checked={centered}
      aria-hidden={hidden}
      tabIndex={centered ? 0 : -1}
      onClick={onSelect}
      style={style}
      // group 으로 묶어 면 위에 올렸을 때만 기본 정보가 뜨게 한다.
      // motion-reduce 는 움직임을 줄여 달라는 설정을 존중한다.
      className={`group absolute left-1/2 top-1/2 w-64 h-44 rounded-2xl p-5
        flex flex-col justify-between text-left
        bg-gradient-to-br ${face} text-white shadow-xl
        transition-all duration-500 ease-out motion-reduce:transition-none
        focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-2
        ${centered ? 'ring-2 ring-white/40' : 'hover:opacity-90'}`}
    >
      <div className="flex items-start justify-between gap-2">
        <span className="text-xs text-white/70">{card.issuer}</span>
        {card.isDemo && (
          <span className="inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium bg-white/20 text-white/90">
            시연용
          </span>
        )}
      </div>

      <div>
        <p className="text-base font-semibold leading-snug">{card.cardName}</p>
        <p className="text-xs text-white/70 mt-0.5">매월 {card.paymentDay}일 결제</p>
      </div>

      {/* 기본 정보. 마우스를 올리거나 이 카드가 가운데일 때만 보인다.
          자리는 늘 차지하게 두고 투명도만 바꾼다 — 나타날 때 카드 안에서
          글자가 밀리면 겹쳐 보인다. */}
      <div
        className={`h-14 transition-opacity duration-300 motion-reduce:transition-none ${
          centered ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
        }`}
      >
        <p className="text-lg font-bold tabular-nums leading-none">
          {formatWon(card.perfCurrent)}
        </p>
        <div className="mt-1.5 h-1 rounded-full bg-white/20 overflow-hidden">
          <div
            className="h-full rounded-full bg-white/80 transition-[width] duration-500 motion-reduce:transition-none"
            style={{ width: `${progressRatio(card) * 100}%` }}
          />
        </div>
        <p className="text-xs text-white/70 mt-1">
          {active ? '혜택 적용 중' : `${formatWon(remaining)} 더 쓰면 혜택 시작`}
        </p>
      </div>
    </button>
  );
}
