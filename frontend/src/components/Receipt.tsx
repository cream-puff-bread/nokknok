import type { ReactNode } from 'react';

import { ClauseList } from './ClauseList';
import { Skeleton } from './Skeleton';
import {
  formatWon,
  PAYMENT_TYPE_LABEL,
  type ParsedQuery,
  type RouteResponse,
} from '../types/contract';

interface ReceiptProps {
  purchase: ParsedQuery;
  categoryLabel: (code: string) => string;
  /** 어느 카드로 결제할지. 아직 계산 중이면 loading 을 켠다. */
  route?: RouteResponse | null;
  routeLoading?: boolean;
  /** 결제 방식별 잔고 추이. 2번 자리에 그대로 들어간다. */
  forecast?: ReactNode;
}

/**
 * 결제 영수증.
 *
 * 추천 결과와 잔고 영향을 표 두 개로 나눠 놓으면 이용자가 둘을 머릿속에서
 * 합쳐야 한다. 영수증 한 장에 "얼마를", "어느 카드로", "그래서 잔고가
 * 어떻게 되는지" 를 세로로 쌓으면 그 자리에서 판단이 끝난다.
 *
 * 세 칸에 번호를 매긴다. 읽는 순서가 곧 판단하는 순서다 — 무엇을 사는지,
 * 어느 카드가 유리한지, 그러고 나면 잔고가 버티는지. 번호가 없으면 어디부터
 * 봐야 하는지가 글자 크기로만 암시된다.
 *
 * 근거 약관을 맨 아래 작은 글씨로 두는 것도 형식과 내용이 맞아떨어진다 —
 * 실제 영수증의 약관 자리에 진짜 약관 조항이 들어간다. 다른 도구는 할인액
 * 까지는 내놓아도 이 칸을 채우지 못한다.
 */
export function Receipt({
  purchase,
  categoryLabel,
  route,
  routeLoading = false,
  forecast,
}: ReceiptProps) {
  const best = route?.best ?? null;

  return (
    <article className="overflow-hidden rounded-xl border border-gray-200 bg-white">
      <header className="flex items-end justify-between gap-4 border-b border-dashed border-gray-300 px-6 py-5">
        <div>
          <p className="text-xs text-gray-500">
            {categoryLabel(purchase.category)} · {PAYMENT_TYPE_LABEL[purchase.paymentType]}
            {purchase.installmentMonths > 0 && ` ${purchase.installmentMonths}개월`}
          </p>
          <p className="text-sm text-gray-500">결제 예정 금액</p>
        </div>
        <span className="text-2xl font-bold tabular-nums text-gray-900">
          {formatWon(purchase.amount)}
        </span>
      </header>

      <Section step={1} title="엔진이 고른 최적 카드">
        {routeLoading && (
          <dl className="space-y-3">
            <Row label="카드">
              <Skeleton className="h-4 w-40" />
            </Row>
            <Row label="예상 할인">
              <Skeleton className="h-4 w-20" />
            </Row>
          </dl>
        )}
        {best && (
          <div className="rounded-2xl border border-gray-100 bg-gray-50 p-4">
            <div className="flex items-center gap-3">
              {/* 실물 카드 비율의 미니 플레이트. 번호는 넣지 않는다 — 카드
                  번호는 우리 데이터에 없어서 넣으려면 지어내야 한다. */}
              <div
                aria-hidden
                className="h-11 w-16 shrink-0 rounded-lg bg-gradient-to-br from-slate-700 to-slate-500"
              />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold text-gray-900">
                  {best.cardName}
                  {best.isDemo && (
                    <span className="ml-2 inline-flex items-center rounded-md bg-gray-200 px-1.5 py-0.5 text-[10px] font-medium text-gray-600">
                      시연용
                    </span>
                  )}
                </p>
                <p className="text-xs text-gray-500">
                  실적 {formatWon(best.perfCurrent)} / {formatWon(best.perfRequired)}
                  <span
                    className={`ml-1.5 ${
                      best.perfAchieved ? 'text-emerald-600' : 'text-amber-600'
                    }`}
                  >
                    {best.perfAchieved ? '충족' : '미충족'}
                  </span>
                </p>
              </div>
              <div className="shrink-0 text-right">
                <p className="text-xs text-gray-500">할인</p>
                <p className="text-base font-bold tabular-nums text-blue-600">
                  −{formatWon(best.expectedDiscount)}
                </p>
              </div>
            </div>

            {/* "실 결제액" 이라고 쓰지 않는다. 카드 할인은 청구 시 차감이나
                캐시백으로 돌아오는 것이 보통이라 결제 순간 금액이 줄지 않고,
                우리 규칙 테이블에도 어느 쪽인지가 없다. 금액을 다루는 화면이라
                단정하지 않고 "할인 반영 후" 로 적는다. */}
            <div className="mt-3 flex items-baseline justify-between gap-4 border-t border-gray-200 pt-3">
              <span className="text-sm text-gray-500">할인 반영 후</span>
              <span className="text-lg font-extrabold tabular-nums text-gray-900">
                {formatWon(purchase.amount - best.expectedDiscount)}
              </span>
            </div>
          </div>
        )}
        {!routeLoading && !best && (
          <p className="text-sm text-gray-500">추천할 카드를 찾지 못했습니다.</p>
        )}
      </Section>

      {forecast !== undefined && (
        <Section step={2} title="향후 6개월 잔고">
          {forecast}
        </Section>
      )}

      {best && best.clauses.length > 0 && (
        // 영수증 하단 약관 자리에 진짜 약관 조항이 들어간다. 다만 본문의
        // 절반을 차지하면 결론이 묻히므로 접어 두고 원할 때 펴게 한다.
        <details className="group border-b border-dashed border-gray-300 px-6 py-4">
          <summary className="flex cursor-pointer list-none items-center gap-1 text-xs text-gray-500 hover:text-gray-900">
            3. 적용된 카드 약관 보기
            <svg
              viewBox="0 0 24 24"
              className="h-3 w-3 transition-transform group-open:rotate-180"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
            >
              <path d="m6 9 6 6 6-6" />
            </svg>
          </summary>
          <div className="mt-3">
            <ClauseList clauses={best.clauses} />
          </div>
        </details>
      )}

      {/* 심사위원이 혼자 둘러보는 화면이다. 카드 뱃지만으로는 "이 계산이
          실제 결제로 이어지지 않는다" 가 분명하지 않아 한 줄로 못박는다. */}
      <footer className="px-6 py-3 text-center text-xs text-gray-400">
        데모 시뮬레이션입니다 · 실제 결제는 이뤄지지 않습니다
      </footer>
    </article>
  );
}

function Section({
  step,
  title,
  tone = 'plain',
  children,
}: {
  step: number;
  title: string;
  tone?: 'plain' | 'muted';
  children: ReactNode;
}) {
  return (
    <section
      className={`border-b border-dashed border-gray-300 px-6 py-5 ${
        tone === 'muted' ? 'bg-gray-50' : ''
      }`}
    >
      <h4 className="mb-3 text-xs font-medium text-gray-500">
        {step}. {title}
      </h4>
      {children}
    </section>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className="shrink-0 text-sm text-gray-500">{label}</dt>
      <dd className="text-right text-sm text-gray-900">{children}</dd>
    </div>
  );
}
