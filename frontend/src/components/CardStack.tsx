import { useEffect, useRef, useState, type KeyboardEvent } from 'react';

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
 * 누른 카드가 앞으로 오기 전에 위로 솟는 거리.
 *
 * 팀원 시안은 카드 높이의 130% 를 썼는데, 그건 카드가 한 장뿐인 지갑이라
 * 가능했다. 우리 덱은 위에 "내 카드" 제목이 붙어 있어 그만큼 솟으면 제목을
 * 덮는다. 한 칸 간격(72px)보다 조금 작게 잡아 "뽑혔다" 가 보이는 만큼만 든다.
 */
const PULL_LIFT = 64;

/**
 * 솟는 데 걸리는 시간과, 앞자리로 내려앉는 데 걸리는 시간.
 *
 * 두 값은 각 단계의 CSS 전이 시간과 **정확히 같아야 한다**. 처음에는 솟는
 * 전이가 300ms 인데 자리를 380ms 뒤에 바꿨더니, 그 사이 80ms 동안 카드가 위에
 * 멈춰 있어 한 동작이 아니라 두 동작으로 끊겨 보였다.
 *
 * 내려앉는 쪽을 더 길게 둔다. 뽑을 때는 짧게 채고 넣을 때는 미끄러지듯
 * 들어가는 편이 손으로 카드를 다루는 느낌에 가깝다.
 *
 * 이 두 단계가 도는 동안에는 다른 카드를 눌러도 받지 않는다 — 순서를 실제로
 * 바꾸는 동작이라 겹치면 어느 카드가 어디로 가는지 알 수 없다.
 */
const PULL_MS = 300;
const SETTLE_MS = 540;

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
 * 뒤 카드를 누르면 지갑에서 한 장 뽑듯 위로 솟았다가 맨 앞자리로 내려앉는다.
 * 앞에 선 카드를 누르면 혜택 구간과 제외 항목이 열린다. 같은 클릭이지만 카드가
 * 어디 있느냐로 갈린다 — 뒤에 있으면 꺼내고, 앞에 있으면 들여다본다.
 *
 * 마우스를 올리는 것만으로는 아무것도 움직이지 않는다. 올린 카드를 앞으로
 * 끌어내 봤는데, 카드가 커서 밑에서 빠져나가면 그 자리에 다른 카드가 들어오고
 * 그것이 또 호버로 잡혀 두 장이 서로를 밀어냈다. 순서를 바꾸는 일은 사람이
 * 분명히 누른 것에만 맡긴다.
 */
export function CardStack({ cards, onSelect }: CardStackProps) {
  // 화면에 쌓인 순서. 값은 cards 의 인덱스이고, 배열 앞쪽이 위(뒤)다.
  //
  // 응답 배열을 그대로 쓰지 않고 따로 들고 있는 이유는 누를 때마다 순서가
  // 바뀌기 때문이다. cards 자체를 건드리지 않으므로 상위가 다시 받아 와도
  // 원래 순서가 남는다.
  const ids = cards.map((c) => c.cardId).join(',');
  const [stack, setStack] = useState<number[]>(() => cards.map((_, i) => i).reverse());
  const [moving, setMoving] = useState<{ card: number; phase: 'pull' | 'settle' } | null>(null);
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const timer = useRef<number | null>(null);

  // 사례를 바꾸면 카드가 통째로 갈린다. 그때는 쌓인 순서도 처음으로 되돌린다.
  useEffect(() => {
    setStack(cards.map((_, i) => i).reverse());
    setMoving(null);
    // 카드 목록이 실제로 바뀐 경우만 본다. cards 는 렌더마다 새 배열일 수 있다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ids]);

  useEffect(
    () => () => {
      if (timer.current !== null) window.clearTimeout(timer.current);
    },
    [],
  );

  const height = (cards.length - 1) * STACK_GAP + CARD_HEIGHT;
  const frontAt = stack.length - 1;

  // 누른 카드를 위로 솟게 했다가 맨 앞자리로 내려놓는다. 이미 앞에 선 카드는
  // 옮길 곳이 없으므로 그대로 자세히 보기로 넘긴다.
  const press = (position: number) => {
    if (moving !== null) return;
    if (position === frontAt) {
      onSelect(cards[stack[position]]);
      return;
    }
    const card = stack[position];
    setMoving({ card, phase: 'pull' });

    // 솟기가 끝나는 그 순간에 자리를 바꾼다. 바뀐 자리로 가는 것도 전이라,
    // 카드는 멈추지 않고 솟은 높이에서 앞자리까지 이어서 미끄러진다.
    timer.current = window.setTimeout(() => {
      setStack((prev) => [...prev.filter((c) => c !== card), card]);
      setMoving({ card, phase: 'settle' });
      timer.current = window.setTimeout(() => setMoving(null), SETTLE_MS);
    }, PULL_MS);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, position: number) => {
    const delta = event.key === 'ArrowDown' ? 1 : event.key === 'ArrowUp' ? -1 : 0;
    if (delta === 0) return;
    event.preventDefault();
    const next = stack[(position + delta + stack.length) % stack.length];
    refs.current[next]?.focus();
  };

  return (
    <div className="relative" style={{ height }}>
      {/* 그리는 순서는 cards 그대로 두고 쌓인 자리는 top·z 로만 만든다.
          stack 순서대로 그리면 순서가 바뀔 때 React 가 DOM 노드를 실제로
          옮기는데, 옮겨진 노드는 돌고 있던 CSS 전이가 초기화된다. 그러면
          앞자리로 내려앉는 동작이 통째로 건너뛰어 순간이동처럼 보인다(실측). */}
      {cards.map((card, cardIndex) => {
        const position = stack.indexOf(cardIndex);
        const active = card.benefits.some((b) => b.active);
        const remaining = (card.perfNextThreshold ?? 0) - card.perfCurrent;
        const isFront = position === frontAt;
        const phase = moving?.card === cardIndex ? moving.phase : null;
        // 내려앉는 동안에도 맨 위에 있어야 다른 카드 뒤로 숨지 않고 미끄러진다.
        const lifted = phase !== null;

        return (
          <button
            key={card.cardId}
            ref={(el) => {
              refs.current[cardIndex] = el;
            }}
            type="button"
            onKeyDown={(event) => onKeyDown(event, position)}
            onClick={() => press(position)}
            aria-label={
              isFront ? `${card.cardName} 자세히 보기` : `${card.cardName} 앞으로 가져오기`
            }
            style={{
              top: position * STACK_GAP,
              // 솟는 동안에는 모든 카드 위로. 그러지 않으면 앞 카드에 가려
              // 뽑히는 게 안 보인다.
              zIndex: lifted ? stack.length : position,
              height: CARD_HEIGHT,
              // 솟을 때 옆으로도 조금 빠진다. 수직으로만 오르내리면 자리를 옮기는
              // 것이 아니라 위아래로 튀는 것처럼 보인다.
              transform:
                phase === 'pull' ? `translate(10px, -${PULL_LIFT}px) scale(1.04)` : undefined,
              transitionDuration: `${phase === 'pull' ? PULL_MS : SETTLE_MS}ms`,
              // 뽑을 때는 짧게 채고, 넣을 때는 미끄러지듯.
              transitionTimingFunction:
                phase === 'pull' ? 'cubic-bezier(.4,0,.2,1)' : 'cubic-bezier(.2,.8,.25,1)',
            }}
            className={`absolute inset-x-0 text-left
              transition-[top,transform,filter] motion-reduce:transition-none
              rounded-3xl focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-2
              ${lifted ? 'drop-shadow-2xl' : 'drop-shadow-lg hover:drop-shadow-2xl'}`}
          >
            <BankCard
              className="h-full rounded-3xl ring-1 ring-black/40"
              // 바탕은 자리를 따르고 강조색은 카드를 따른다. 앞으로 나올수록
              // 밝아지는 것은 빛을 받는 것처럼 읽혀 자연스럽지만, 카드마다 정한
              // 색까지 자리를 따라 바뀌면 다른 카드가 온 것처럼 보인다.
              surface={CARD_SURFACES[position % CARD_SURFACES.length]}
              accent={CARD_ACCENTS[cardIndex % CARD_ACCENTS.length]}
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
                    <span className="rounded-md bg-white/10 px-2 py-0.5 text-[11px] font-medium text-white/70">
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
                  isFront ? 'opacity-100' : 'opacity-0'
                }`}
              >
                <div className="h-1 overflow-hidden rounded-full bg-white/20">
                  <div
                    className="h-full rounded-full bg-white/80 transition-[width] duration-500 motion-reduce:transition-none"
                    style={{ width: `${progressRatio(card) * 100}%` }}
                  />
                </div>
                <p className="mt-1 text-[11px] text-white/60">
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
