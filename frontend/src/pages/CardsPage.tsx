import { useCallback, useEffect, useState } from 'react';

import { fetchOwnedCards } from '../api/cards';
import {
  ApiRequestError,
  SLOW_REQUEST_MESSAGE,
  type SlowRequestPhase,
} from '../api/client';
import { EmptyState } from '../components/EmptyState';
import { ErrorState } from '../components/ErrorState';
import { PersonaNotFoundAction } from '../components/PersonaNotFoundAction';
import { Skeleton } from '../components/Skeleton';
import {
  formatDate,
  formatWon,
  type ApiErrorCode,
  type CardBenefit,
  type CardExclusion,
  type OwnedCard,
} from '../types/contract';

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string; code?: ApiErrorCode }
  | { status: 'loaded'; cards: OwnedCard[] };

interface CardsPageProps {
  personaId: number;
  onNavigateToPersonas?: () => void;
}

/**
 * 카드 면 색. 카드에 색 정보가 없으므로 보유 순서로 배정한다.
 *
 * 어두운 색만 쓰는 이유는 ui-system.md 가 초록=성공, 호박=주의로 의미를
 * 배정해 뒀기 때문이다. 카드 면에 그 색을 쓰면 "이 카드가 좋다/나쁘다" 로
 * 잘못 읽힌다. 카드는 신원 표시일 뿐이라 의미를 담지 않는다.
 */
const CARD_FACES = [
  'from-slate-800 to-slate-600',
  'from-blue-800 to-blue-600',
  'from-violet-800 to-violet-600',
];

export function CardsPage({ personaId, onNavigateToPersonas }: CardsPageProps) {
  const [state, setState] = useState<LoadState>({ status: 'loading' });
  const [slowPhase, setSlowPhase] = useState<SlowRequestPhase | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const load = useCallback(() => {
    setState({ status: 'loading' });
    setSlowPhase(null);
    fetchOwnedCards(personaId, { onSlowRequest: setSlowPhase })
      .then((cards) => {
        setState({ status: 'loaded', cards });
        // 처음에는 첫 카드를 펴 둔다. 아무것도 안 열려 있으면 화면이 비어
        // 보이고, 무엇을 눌러야 하는지도 알기 어렵다.
        setSelectedId(cards[0]?.cardId ?? null);
      })
      .catch((err: unknown) => {
        if (err instanceof ApiRequestError) {
          setState({ status: 'error', message: err.message, code: err.code });
          return;
        }
        setState({ status: 'error', message: '보유 카드를 불러오지 못했습니다.' });
      });
  }, [personaId]);

  useEffect(load, [load]);

  const selected =
    state.status === 'loaded'
      ? (state.cards.find((c) => c.cardId === selectedId) ?? null)
      : null;

  return (
    <section className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-gray-900 mb-1">내 카드</h3>
        <p className="text-sm text-gray-500">
          카드를 고르면 이번 실적과 지금 열려 있는 혜택, 실적에서 빠지는 항목을 보여줍니다.
        </p>
      </div>

      {state.status === 'loading' && (
        <div className="space-y-6">
          {slowPhase && <p className="text-xs text-gray-500">{SLOW_REQUEST_MESSAGE[slowPhase]}</p>}
          <div className="flex gap-4">
            <Skeleton className="h-44 w-72 rounded-2xl" />
            <Skeleton className="h-44 w-72 rounded-2xl" />
          </div>
          <Skeleton className="h-64 w-full rounded-xl" />
        </div>
      )}

      {state.status === 'error' &&
        (state.code === 'PERSONA_NOT_FOUND' ? (
          <ErrorState
            message={state.message}
            action={<PersonaNotFoundAction onNavigateToPersonas={onNavigateToPersonas} />}
          />
        ) : (
          <ErrorState message={state.message} onRetry={load} />
        ))}

      {state.status === 'loaded' &&
        (state.cards.length === 0 ? (
          <EmptyState message="보유한 카드가 없습니다." />
        ) : (
          <>
            <div
              role="radiogroup"
              aria-label="카드 선택"
              className="flex gap-4 overflow-x-auto pb-2"
            >
              {state.cards.map((card, i) => (
                <CardFace
                  key={card.cardId}
                  card={card}
                  face={CARD_FACES[i % CARD_FACES.length]}
                  selected={card.cardId === selectedId}
                  onSelect={() => setSelectedId(card.cardId)}
                />
              ))}
            </div>

            {selected && <CardDetail card={selected} />}
          </>
        ))}
    </section>
  );
}

/** 실적을 다음 문턱 대비 비율로. 문턱이 없거나 이미 넘겼으면 100% 로 둔다. */
function progressRatio(card: OwnedCard): number {
  if (card.perfNextThreshold === null || card.perfNextThreshold === 0) return 1;
  return Math.min(1, card.perfCurrent / card.perfNextThreshold);
}

function CardFace({
  card,
  face,
  selected,
  onSelect,
}: {
  card: OwnedCard;
  face: string;
  selected: boolean;
  onSelect: () => void;
}) {
  const active = card.benefits.some((b) => b.active);
  const ratio = progressRatio(card);

  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      onClick={onSelect}
      className={`shrink-0 w-72 text-left rounded-2xl p-5 bg-gradient-to-br ${face} text-white transition-all ${
        selected
          ? 'ring-2 ring-blue-600 ring-offset-2 shadow-lg'
          : 'opacity-75 hover:opacity-100'
      }`}
    >
      <div className="flex items-start justify-between gap-2 mb-6">
        <span className="text-xs text-white/70">{card.issuer}</span>
        {card.isDemo && (
          <span className="inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium bg-white/20 text-white/90">
            시연용
          </span>
        )}
      </div>

      <p className="text-base font-semibold leading-snug mb-1">{card.cardName}</p>
      <p className="text-xs text-white/70 mb-4">매월 {card.paymentDay}일 결제</p>

      <p className="text-xl font-bold tabular-nums">{formatWon(card.perfCurrent)}</p>
      {/* 카드 면에 실적 진행을 얹는다. 이름만 있는 카드는 고를 근거가 없다. */}
      <div className="mt-2 h-1.5 rounded-full bg-white/20 overflow-hidden">
        <div className="h-full rounded-full bg-white/80" style={{ width: `${ratio * 100}%` }} />
      </div>
      <p className="text-xs text-white/70 mt-1.5">
        {active ? '혜택 적용 중' : `${formatWon((card.perfNextThreshold ?? 0) - card.perfCurrent)} 남음`}
      </p>
    </button>
  );
}

function CardDetail({ card }: { card: OwnedCard }) {
  const shortfall =
    card.perfNextThreshold !== null && card.perfCurrent < card.perfNextThreshold
      ? card.perfNextThreshold - card.perfCurrent
      : 0;

  return (
    <article className="bg-white rounded-xl border border-gray-200 p-6 space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs text-gray-500 mb-1">
            이번 실적 · {formatDate(card.perfPeriodStart)}~{formatDate(card.perfPeriodEnd)}
          </p>
          <p className="text-3xl font-bold tabular-nums text-gray-900">
            {formatWon(card.perfCurrent)}
          </p>
          {shortfall > 0 && (
            <p className="text-sm text-amber-600 mt-1">
              <span className="tabular-nums">{formatWon(shortfall)}</span> 더 쓰면 혜택이 열립니다
            </p>
          )}
        </div>
        {card.monthlyCap !== null && (
          <div className="text-right">
            <p className="text-xs text-gray-500 mb-1">월 통합 한도</p>
            <p className="text-sm text-gray-900 tabular-nums">{formatWon(card.monthlyCap)}</p>
          </div>
        )}
      </div>

      {card.benefits.length > 0 && <BenefitTable benefits={card.benefits} />}
      {card.exclusions.length > 0 && <ExclusionList exclusions={card.exclusions} />}
    </article>
  );
}

/**
 * 실적 구간을 전부 보여준다. 지금 적용되는 것만 보여주면 계단형 카드의
 * 가치가 드러나지 않는다 — "지금은 5%인데 50만원을 넘기면 7%" 가 보여야
 * 실적을 채울 이유가 생긴다.
 */
function BenefitTable({ benefits }: { benefits: CardBenefit[] }) {
  return (
    <div>
      <h4 className="text-xs text-gray-500 mb-2">실적 구간별 혜택</h4>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-gray-500 text-left">
              <th className="font-normal py-1 pr-4">실적 구간</th>
              <th className="font-normal py-1 pr-4">분류</th>
              <th className="font-normal py-1 pr-4 text-right">할인율</th>
              <th className="font-normal py-1 text-right">월 한도</th>
            </tr>
          </thead>
          <tbody>
            {benefits.map((b, i) => (
              <tr
                key={i}
                className={
                  b.active ? 'bg-blue-50 text-gray-900' : 'text-gray-500 border-t border-gray-100'
                }
              >
                <td className="py-1.5 pr-4 tabular-nums whitespace-nowrap">
                  {formatWon(b.perfMin)}
                  {b.perfMax === null ? ' 이상' : ` ~ ${formatWon(b.perfMax)}`}
                </td>
                <td className="py-1.5 pr-4 whitespace-nowrap">
                  {b.categoryLabel}
                  {b.active && <span className="ml-2 text-xs text-blue-600">적용 중</span>}
                </td>
                <td className="py-1.5 pr-4 text-right tabular-nums">
                  {(b.discountRate * 100).toFixed(0)}%
                </td>
                <td className="py-1.5 text-right tabular-nums whitespace-nowrap">
                  {b.categoryCap === null ? '—' : formatWon(b.categoryCap)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const EXCLUSION_EFFECT: Record<CardExclusion['exclusionType'], string> = {
  PERFORMANCE: '실적 미인정',
  DISCOUNT: '할인 제외',
  BOTH: '실적·할인 모두 제외',
};

/**
 * 카드사 앱이 알려주지 않는 부분이다. 약관에서 뽑아낸 값이라 이 화면에서
 * 가장 설명이 필요한 항목이기도 하다 — 무이자 할부로 결제하면 실적이
 * 쌓이지 않는다는 걸 모르고 쓰는 경우가 많다.
 */
function ExclusionList({ exclusions }: { exclusions: CardExclusion[] }) {
  const grouped = exclusions.reduce<Record<string, string[]>>((acc, e) => {
    (acc[e.exclusionType] ??= []).push(e.targetLabel);
    return acc;
  }, {});

  return (
    <div>
      <h4 className="text-xs text-gray-500 mb-2">제외 항목</h4>
      <ul className="space-y-1">
        {Object.entries(grouped).map(([type, labels]) => (
          <li key={type} className="text-sm text-gray-900">
            <span className="text-gray-500">
              {EXCLUSION_EFFECT[type as CardExclusion['exclusionType']]}
            </span>{' '}
            {labels.join(', ')}
          </li>
        ))}
      </ul>
    </div>
  );
}
