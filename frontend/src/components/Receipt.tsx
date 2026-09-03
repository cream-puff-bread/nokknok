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
      <header className="border-b border-dashed border-gray-300 px-6 py-5">
        <p className="mb-1 text-xs text-gray-500">
          {categoryLabel(purchase.category)} · {PAYMENT_TYPE_LABEL[purchase.paymentType]}
          {purchase.installmentMonths > 0 && ` ${purchase.installmentMonths}개월`}
        </p>
        <div className="flex items-baseline justify-between gap-4">
          <span className="text-sm text-gray-500">결제 예정 금액</span>
          <span className="text-2xl font-bold tabular-nums text-gray-900">
            {formatWon(purchase.amount)}
          </span>
        </div>
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
          <dl className="space-y-3">
            <Row label="카드">
              <span className="font-medium">{best.cardName}</span>
              {best.isDemo && (
                <span className="ml-2 inline-flex items-center rounded-md bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-500">
                  시연용
                </span>
              )}
            </Row>
            <Row label="실적">
              <span className="tabular-nums">
                {formatWon(best.perfCurrent)} / {formatWon(best.perfRequired)}
              </span>
              <span
                className={`ml-2 text-xs ${
                  best.perfAchieved ? 'text-emerald-600' : 'text-amber-600'
                }`}
              >
                {best.perfAchieved ? '충족' : '미충족'}
              </span>
            </Row>
            <Row label="예상 할인">
              <span className="text-lg font-bold tabular-nums text-blue-600">
                −{formatWon(best.expectedDiscount)}
              </span>
            </Row>
          </dl>
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
        // 영수증 하단 약관 자리에 진짜 약관 조항이 들어간다.
        <Section step={3} title="근거 약관" tone="muted">
          <ClauseList clauses={best.clauses} />
        </Section>
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
