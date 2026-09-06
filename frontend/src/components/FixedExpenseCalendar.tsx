import { useEffect, useMemo, useState } from 'react';

import { fetchOwnedCards } from '../api/cards';
import {
  EXPENSE_TYPE_LABEL,
  formatWon,
  type DayBalance,
  type FixedExpense,
  type OwnedCard,
} from '../types/contract';

interface FixedExpenseCalendarProps {
  fixedExpenses: FixedExpense[];
  personaId: number;
  /** 계산 기준일 'YYYY-MM-DD'. 브라우저 시계를 쓰지 않는 이유는 아래 주석 참고. */
  referenceDate: string;
  incomeDay: number;
  monthlyIncome: number;
  monthOutlook: DayBalance[];
}

/** 한 날짜에 걸린 일. 확정 지출·카드 결제일·급여일을 같은 모양으로 다룬다. */
type DayItem =
  | { kind: 'expense'; label: string; amount: number; badge: string; unusedSuspect: boolean }
  | { kind: 'card'; label: string }
  | { kind: 'income'; label: string; amount: number };

/**
 * 확정 지출·카드 결제일 달력.
 *
 * `chargeDay`·`paymentDay` 는 "매달 며칠" 이라는 반복 값이라 실제 요일에 걸려
 * 있지 않다(이번 달 5일이 화요일이어도 다음 달 5일은 아니다). 그래서 진짜
 * 달력처럼 요일을 맞추지 않고 1~31 을 순서대로 늘어놓는다. 요일을 맞추면
 * 없는 정보를 있는 것처럼 보이게 만든다.
 *
 * 오늘과 위험한 날은 서버가 준 값으로만 정한다. `new Date()` 를 쓰면 브라우저
 * 시계(실제 오늘)로 판단하게 되는데 서버는 DEMO_TODAY 로 고정돼 있어, 달력의
 * "오늘" 만 다른 날에 찍히고 나머지 숫자와 어긋난다.
 *
 * 적자 판정도 새로 만들지 않는다. `monthOutlook[].balance < 0` 하나만 보며,
 * 그 값은 백엔드가 그래프와 같은 규칙으로 계산한 것이다(forecast/daily.py).
 * 달력만 다른 기준을 쓰면 같은 화면 안에서 두 그림이 다른 말을 하게 된다.
 */
export function FixedExpenseCalendar({
  fixedExpenses,
  personaId,
  referenceDate,
  incomeDay,
  monthlyIncome,
  monthOutlook,
}: FixedExpenseCalendarProps) {
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
    push(incomeDay, { kind: 'income', label: '급여', amount: monthlyIncome });
    return map;
  }, [fixedExpenses, cards, incomeDay, monthlyIncome]);

  // 브라우저 시계가 아니라 서버가 계산에 쓴 날이다.
  const today = Number(referenceDate.slice(8, 10));
  const outlookByDay = useMemo(
    () => new Map(monthOutlook.map((point) => [point.day, point])),
    [monthOutlook],
  );
  const firstShortfall = monthOutlook.find((point) => point.balance < 0) ?? null;

  const [selectedDay, setSelectedDay] = useState<number | null>(null);
  // 고른 날이 비는 경우(카드 조회가 늦게 붙는 등)에는 선택을 풀어 둔다.
  const selected = selectedDay === null ? [] : (byDay.get(selectedDay) ?? []);
  const selectedOutlook = selectedDay === null ? undefined : outlookByDay.get(selectedDay);

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4">
      <div className="mb-3 flex items-center justify-between gap-4">
        {/* 어느 날이 오늘인지 글로도 적는다. 테두리만으로는 무슨 표시인지
            알 수 없고, 기준일이 실제 오늘이 아닐 수 있어(DEMO_TODAY) 날짜를
            밝히지 않으면 화면의 다른 숫자와 왜 다른지 설명할 길이 없다. */}
        <p className="text-xs text-gray-400">
          테두리가 진한 {today}일이 기준일입니다 · 반복되는 날짜라 요일과는 무관합니다
        </p>
        <div className="flex shrink-0 items-center gap-3 text-xs text-gray-500">
          <Legend className="bg-blue-500">확정 지출</Legend>
          <Legend className="bg-slate-400">카드 결제</Legend>
          <Legend className="bg-emerald-500">입금</Legend>
        </div>
      </div>

      <div className="grid grid-cols-7 gap-1">
        {Array.from({ length: 31 }, (_, i) => i + 1).map((day) => {
          const items = byDay.get(day);
          const outlook = outlookByDay.get(day);
          const isSelected = selectedDay === day;
          const isToday = day === today;
          const short = outlook !== undefined && outlook.balance < 0;
          const hasExpense = items?.some((i) => i.kind === 'expense') ?? false;
          const hasCard = items?.some((i) => i.kind === 'card') ?? false;
          const hasIncome = items?.some((i) => i.kind === 'income') ?? false;
          // 예상 잔고만 있는 날도 누를 수 있어야 한다. 나가는 게 없는데
          // 잔고가 모자라는 날이 생기기 때문이다(그 전날까지 쌓인 결과).
          const active = items !== undefined || outlook !== undefined;

          return (
            <button
              key={day}
              type="button"
              disabled={!active}
              aria-pressed={isSelected}
              aria-label={
                isToday ? `${day}일 (오늘)` : short ? `${day}일 (잔고 부족)` : `${day}일`
              }
              onClick={() => setSelectedDay(isSelected ? null : day)}
              className={`flex aspect-square flex-col items-center justify-center rounded-lg border text-xs transition-colors ${
                isSelected
                  ? 'border-blue-500 bg-blue-50'
                  : isToday
                    ? 'border-gray-900 bg-white hover:bg-gray-50'
                    : short
                      ? 'border-red-200 bg-red-50 hover:bg-red-100'
                      : active
                        ? 'border-gray-200 bg-gray-50 hover:bg-gray-100'
                        : 'border-transparent text-gray-300'
              }`}
            >
              <span
                className={`tabular-nums ${
                  short ? 'font-semibold text-red-600' : active ? 'font-semibold text-gray-900' : ''
                }`}
              >
                {day}
              </span>
              <span className="mt-1 flex h-1.5 items-center gap-0.5">
                {hasExpense && <span className="h-1.5 w-1.5 rounded-full bg-blue-500" />}
                {hasCard && <span className="h-1.5 w-1.5 rounded-full bg-slate-400" />}
                {hasIncome && <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />}
              </span>
            </button>
          );
        })}
      </div>

      {firstShortfall !== null && (
        <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">
          이대로면 {firstShortfall.day}일에 잔고가 {formatWon(-firstShortfall.balance)}{' '}
          모자랍니다.
        </p>
      )}

      {selectedDay === null ? (
        <p className="mt-4 text-center text-sm text-gray-400">
          날짜를 누르면 그날 나가는 돈과 예상 잔고를 보여줍니다.
        </p>
      ) : (
        <div className="mt-4 border-t border-dashed border-gray-200 pt-3">
          <div className="mb-2 flex items-baseline justify-between gap-2">
            <h4 className="text-xs font-medium text-gray-500">
              매달 {selectedDay}일{selectedDay === today && ' · 오늘'}
            </h4>
            {/* 기준일 이전에는 예상 잔고가 없다. 이미 지난 날의 잔고를
                거꾸로 되짚는 건 이 서비스가 가진 데이터로 할 수 없다. */}
            {selectedOutlook !== undefined && (
              <span
                className={`text-xs tabular-nums ${
                  selectedOutlook.balance < 0 ? 'font-semibold text-red-600' : 'text-gray-500'
                }`}
              >
                예상 잔고 {formatWon(selectedOutlook.balance)}
              </span>
            )}
          </div>
          {selected.length === 0 && (
            <p className="text-sm text-gray-400">이 날 정해진 입출금은 없습니다.</p>
          )}
          <ul className="space-y-1.5">
            {selected.map((item, i) => (
              <li
                key={`${item.kind}-${item.label}-${i}`}
                className="flex items-center gap-2 rounded-lg bg-gray-50 px-3 py-2"
              >
                <span
                  className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                    item.kind === 'expense'
                      ? 'bg-blue-500'
                      : item.kind === 'income'
                        ? 'bg-emerald-500'
                        : 'bg-slate-400'
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
                ) : item.kind === 'income' ? (
                  <span className="shrink-0 text-sm tabular-nums text-emerald-700">
                    +{formatWon(item.amount)}
                  </span>
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
