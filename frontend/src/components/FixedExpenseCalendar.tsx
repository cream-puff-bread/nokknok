import { useEffect, useMemo, useState } from 'react';

import { fetchOwnedCards } from '../api/cards';
import {
  EXPENSE_TYPE_LABEL,
  formatWon,
  type FixedExpense,
  type OwnedCard,
} from '../types/contract';

interface FixedExpenseCalendarProps {
  fixedExpenses: FixedExpense[];
  personaId: number;
}

/** 한 날짜에 걸린 돈 나가는 일. 확정 지출과 카드 결제일을 같은 모양으로 다룬다. */
type DayItem =
  | { kind: 'expense'; label: string; amount: number; badge: string; unusedSuspect: boolean }
  | { kind: 'card'; label: string };

/**
 * 확정 지출·카드 결제일 달력.
 *
 * `chargeDay`·`paymentDay` 는 "매달 며칠" 이라는 반복 값이라 실제 요일에 걸려
 * 있지 않다(이번 달 5일이 화요일이어도 다음 달 5일은 아니다). 그래서 진짜
 * 달력처럼 요일을 맞추지 않고 1~31 을 순서대로 늘어놓는다. 요일을 맞추면
 * 없는 정보를 있는 것처럼 보이게 만든다.
 *
 * "이 날 위험" 표시는 넣지 않았다. 기준 날짜가 `date.today()` 라 하루만 지나도
 * 판정이 뒤집히기 때문이다(DEMO_TODAY 고정 후에 별도로 얹는다).
 */
export function FixedExpenseCalendar({ fixedExpenses, personaId }: FixedExpenseCalendarProps) {
  // 카드 결제일은 곁들이는 정보다. 못 받아와도 확정 지출 달력은 그대로
  // 보여준다 — 카테고리 라벨 조회와 같은 규칙이다.
  const [cards, setCards] = useState<OwnedCard[]>([]);

  useEffect(() => {
    let alive = true;
    fetchOwnedCards(personaId)
      .then((loaded) => {
        if (alive) setCards(loaded);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [personaId]);

  const byDay = useMemo(() => {
    const map = new Map<number, DayItem[]>();
    const push = (day: number, item: DayItem) => {
      const list = map.get(day) ?? [];
      list.push(item);
      map.set(day, list);
    };
    for (const expense of fixedExpenses) {
      push(expense.chargeDay, {
        kind: 'expense',
        label: expense.label,
        amount: expense.amount,
        badge: EXPENSE_TYPE_LABEL[expense.expenseType],
        unusedSuspect: expense.unusedSuspect,
      });
    }
    for (const card of cards) {
      push(card.paymentDay, { kind: 'card', label: card.cardName });
    }
    return map;
  }, [fixedExpenses, cards]);

  const [selectedDay, setSelectedDay] = useState<number | null>(null);
  // 고른 날이 비는 경우(카드 조회가 늦게 붙는 등)에는 선택을 풀어 둔다.
  const selected = selectedDay === null ? [] : (byDay.get(selectedDay) ?? []);

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4">
      <div className="mb-3 flex items-center justify-between gap-4">
        <p className="text-xs text-gray-400">매달 반복되는 날짜라 요일과는 무관합니다.</p>
        <div className="flex shrink-0 items-center gap-3 text-xs text-gray-500">
          <Legend className="bg-blue-500">확정 지출</Legend>
          <Legend className="bg-slate-400">카드 결제</Legend>
        </div>
      </div>

      <div className="grid grid-cols-7 gap-1">
        {Array.from({ length: 31 }, (_, i) => i + 1).map((day) => {
          const items = byDay.get(day);
          const isSelected = selectedDay === day;
          const hasExpense = items?.some((i) => i.kind === 'expense') ?? false;
          const hasCard = items?.some((i) => i.kind === 'card') ?? false;

          return (
            <button
              key={day}
              type="button"
              disabled={!items}
              aria-pressed={isSelected}
              onClick={() => setSelectedDay(isSelected ? null : day)}
              className={`flex aspect-square flex-col items-center justify-center rounded-lg border text-xs transition-colors ${
                isSelected
                  ? 'border-blue-500 bg-blue-50'
                  : items
                    ? 'border-gray-200 bg-gray-50 hover:bg-gray-100'
                    : 'border-transparent text-gray-300'
              }`}
            >
              <span className={`tabular-nums ${items ? 'font-semibold text-gray-900' : ''}`}>
                {day}
              </span>
              <span className="mt-1 flex h-1.5 items-center gap-0.5">
                {hasExpense && <span className="h-1.5 w-1.5 rounded-full bg-blue-500" />}
                {hasCard && <span className="h-1.5 w-1.5 rounded-full bg-slate-400" />}
              </span>
            </button>
          );
        })}
      </div>

      {selectedDay === null ? (
        <p className="mt-4 text-center text-sm text-gray-400">
          날짜를 누르면 그날 나가는 돈을 보여줍니다.
        </p>
      ) : (
        <div className="mt-4 border-t border-dashed border-gray-200 pt-3">
          <h4 className="mb-2 text-xs font-medium text-gray-500">매달 {selectedDay}일</h4>
          <ul className="space-y-1.5">
            {selected.map((item, i) => (
              <li
                key={`${item.kind}-${item.label}-${i}`}
                className="flex items-center gap-2 rounded-lg bg-gray-50 px-3 py-2"
              >
                <span
                  className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                    item.kind === 'expense' ? 'bg-blue-500' : 'bg-slate-400'
                  }`}
                />
                <span className="min-w-0 flex-1 truncate text-sm text-gray-900">{item.label}</span>
                {item.kind === 'expense' ? (
                  <>
                    <Tag>{item.badge}</Tag>
                    {item.unusedSuspect && <Tag tone="amber">미사용 의심</Tag>}
                    <span className="shrink-0 text-sm tabular-nums text-gray-900">
                      {formatWon(item.amount)}
                    </span>
                  </>
                ) : (
                  // 카드 결제 금액은 이번 달 사용액이라 확정 지출과 성격이 다르다.
                  // 금액을 지어내지 않고 날짜만 표시한다.
                  <Tag tone="slate">결제일</Tag>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function Legend({ className, children }: { className: string; children: string }) {
  return (
    <span className="flex items-center gap-1">
      <span className={`h-1.5 w-1.5 rounded-full ${className}`} />
      {children}
    </span>
  );
}

function Tag({ children, tone = 'blue' }: { children: string; tone?: 'blue' | 'amber' | 'slate' }) {
  const toneClass = {
    blue: 'bg-blue-50 text-blue-600',
    amber: 'bg-amber-50 text-amber-600',
    slate: 'bg-gray-100 text-gray-500',
  }[tone];
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded-md px-2 py-0.5 text-xs font-medium ${toneClass}`}
    >
      {children}
    </span>
  );
}
