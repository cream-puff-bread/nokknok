import type { ReactNode } from 'react';

import { ClauseList } from './ClauseList';
import { Skeleton } from './Skeleton';
import {
  formatDate,
  formatWon,
  PAYMENT_TYPE_LABEL,
  type ParsedQuery,
  type RouteCandidate,
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
                {/* 결제일을 반드시 함께 적는다. 엔진은 "언제 결제할지" 도
                    고르므로(engine/route.py 의 결제일 조합) 카드 이름만으로는
                    추천이 절반만 전달된다 — 마감을 넘겨 다음 기간에 붙이라는
                    답일 때 그 조건이 사라진다. 대안 카드 줄과 같은 축이다. */}
                <p className="text-xs text-gray-500">
                  {formatDate(best.payDate)} · {PAYMENT_TYPE_LABEL[best.paymentType]}
                  {best.installmentMonths > 0 && ` ${best.installmentMonths}개월`}
                </p>
                {/* "이 결제일 기준" 을 빼면 카드 목록의 실적과 숫자가 달라
                    보인다. 둘은 다른 기간을 센 값이다 — 카드 목록은 오늘이
                    속한 기간, 여기는 위 결제일이 속한 기간이다. */}
                <p className="text-xs text-gray-500">
                  이 결제일 기준 실적 {formatWon(best.perfCurrent)} /{' '}
                  {formatWon(best.perfRequired)}
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

        {/* LLM 설명. 생성 실패·타임아웃이면 null 이고, 그때는 이 줄만 빠진다 —
            위 카드·할인액은 엔진이 계산한 값이라 그대로 남는다(CLAUDE.md 불변식). */}
        {best?.explanation && (
          <p className="mt-3 border-l-2 border-blue-200 pl-3 text-sm leading-relaxed text-gray-600">
            {best.explanation}
          </p>
        )}

        {/* 대안 카드. 엔진이 비교한 결과가 있는데 안 보여주면 "왜 이 카드인지" 가
            근거 없이 통보처럼 읽힌다. 다만 결론을 밀어내지 않도록 접어 둔다. */}
        {route && route.alternatives.length > 0 && (
          <Disclosure summary={`다른 카드 ${route.alternatives.length}장과 비교`}>
            <ul className="space-y-2">
              {route.alternatives.map((candidate) => (
                <AlternativeRow key={candidate.cardId} candidate={candidate} />
              ))}
            </ul>
          </Disclosure>
        )}

        {!routeLoading && !best && (
          <p className="text-sm text-gray-500">추천할 카드를 찾지 못했습니다.</p>
        )}
      </Section>

      {/* 보유 카드로 조건을 못 채운 경우에만 온다. 계약 주석대로 최적화 결과와
          시각적으로 분리하고 제휴 여부를 함께 밝힌다. */}
      {route?.newCardSuggestion && (
        <div className="border-b border-dashed border-gray-300 bg-amber-50 px-6 py-4">
          <p className="text-xs font-medium text-amber-700">보유 카드로는 조건을 채우지 못했습니다</p>
          <p className="mt-1 text-sm text-gray-900">
            <span className="font-semibold">{route.newCardSuggestion.cardName}</span> 발급 시{' '}
            <span className="font-semibold tabular-nums">
              {formatWon(route.newCardSuggestion.expectedGain)}
            </span>{' '}
            더 받을 수 있습니다.
            {route.newCardSuggestion.isDemo && <Tag>시연용</Tag>}
            {route.newCardSuggestion.isAffiliate && <Tag>제휴</Tag>}
          </p>
        </div>
      )}

      {forecast !== undefined && (
        <Section step={2} title="향후 6개월 잔고">
          {forecast}
        </Section>
      )}

      {best && best.clauses.length > 0 && (
        // 영수증 하단 약관 자리에 진짜 약관 조항이 들어간다. 다만 본문의
        // 절반을 차지하면 결론이 묻히므로 접어 두고 원할 때 펴게 한다.
        <div className="border-b border-dashed border-gray-300 px-6 py-4">
          <Disclosure summary="3. 적용된 카드 약관 보기" flush>
            <ClauseList clauses={best.clauses} />
          </Disclosure>
        </div>
      )}

      {/* 검수 안 된 규칙만 있는 카드를 후보에서 뺐다는 사실. 오류가 아니라
          정상 응답이므로(계약 주석) 경고가 아닌 각주로만 남긴다. */}
      {route && route.computeMeta.excludedUnverifiedCards > 0 && (
        <p className="border-b border-dashed border-gray-300 px-6 py-3 text-xs text-gray-400">
          검수가 끝나지 않은 카드 {route.computeMeta.excludedUnverifiedCards}장은 후보에서
          제외했습니다.
        </p>
      )}

      {/* 심사위원이 혼자 둘러보는 화면이다. 카드 뱃지만으로는 "이 계산이
          실제 결제로 이어지지 않는다" 가 분명하지 않아 한 줄로 못박는다. */}
      <footer className="px-6 py-3 text-center text-xs text-gray-400">
        데모 시뮬레이션입니다 · 실제 결제는 이뤄지지 않습니다
      </footer>
    </article>
  );
}

/** 결론을 밀어내지 않도록 접어 두는 보조 정보. 약관·대안 카드가 같은 모양을 쓴다. */
function Disclosure({
  summary,
  children,
  flush = false,
}: {
  summary: string;
  children: ReactNode;
  flush?: boolean;
}) {
  return (
    <details className={`group ${flush ? '' : 'mt-3'}`}>
      <summary className="flex cursor-pointer list-none items-center gap-1 text-xs text-gray-500 hover:text-gray-900">
        {summary}
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
      <div className="mt-3">{children}</div>
    </details>
  );
}

/**
 * 대안 카드 한 줄.
 *
 * best 와 같은 축(할인액·실적·결제일)만 보여준다 — 비교 대상이 서로 다른 값을
 * 보이면 왜 이 카드가 밀렸는지 읽어내지 못한다.
 */
function AlternativeRow({ candidate }: { candidate: RouteCandidate }) {
  return (
    <li className="flex items-center gap-3 rounded-lg border border-gray-100 bg-gray-50 px-3 py-2">
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm text-gray-900">
          {candidate.cardName}
          {candidate.isDemo && <Tag>시연용</Tag>}
        </p>
        <p className="text-xs text-gray-500">
          {formatDate(candidate.payDate)} · {PAYMENT_TYPE_LABEL[candidate.paymentType]}
          {candidate.installmentMonths > 0 && ` ${candidate.installmentMonths}개월`}
          <span className={`ml-1.5 ${candidate.perfAchieved ? 'text-emerald-600' : 'text-amber-600'}`}>
            실적 {candidate.perfAchieved ? '충족' : '미충족'}
          </span>
        </p>
      </div>
      <span className="shrink-0 text-sm font-semibold tabular-nums text-gray-500">
        −{formatWon(candidate.expectedDiscount)}
      </span>
    </li>
  );
}

function Tag({ children }: { children: ReactNode }) {
  return (
    <span className="ml-1.5 inline-flex items-center rounded-md bg-gray-200 px-1.5 py-0.5 text-[10px] font-medium text-gray-600">
      {children}
    </span>
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
