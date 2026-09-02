import type { ReactNode } from 'react';

interface BankCardProps {
  /** 카드 포인트색(hex). 카드 배경은 항상 어두운 유리질(glassmorphism)
   * 톤이고, 이 색은 모서리에 번지는 은은한 글로우로만 쓰인다 — 참고:
   * 다크 테마 SaaS 랜딩의 프로스티드 글래스 카드 스타일. */
  accent: string;
  brand: string;
  subtitle?: string;
  title: string;
  footer?: string;
  demoBadge?: ReactNode;
  className?: string;
}

export function BankCard({
  accent,
  brand,
  subtitle,
  title,
  footer,
  demoBadge,
  className = '',
}: BankCardProps) {
  return (
    <div
      className={`relative overflow-hidden rounded-2xl border border-white/10 bg-gray-900 shadow-xl ${className}`}
    >
      {/* 모서리 글로우 — 유리질 느낌의 핵심. blur로 은은하게 번지게 한다. */}
      <div
        aria-hidden
        className="pointer-events-none absolute -top-10 -right-10 h-32 w-32 rounded-full blur-3xl opacity-50"
        style={{ backgroundColor: accent }}
      />
      {/* 위에서 비스듬히 들어오는 유리 광택. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-gradient-to-br from-white/10 via-transparent to-transparent"
      />

      <div className="relative h-full p-4 flex flex-col justify-between">
        <div className="flex items-start justify-between">
          <div>
            <span className="block text-xs font-bold uppercase tracking-wide text-white">
              {brand}
            </span>
            {subtitle && (
              <span className="block text-[10px] uppercase tracking-wide text-white/60">
                {subtitle}
              </span>
            )}
          </div>
          {/* 네트워크 로고 자리 — 실물 카드의 마스터카드류 겹친 원 마크를 흉내낸다. */}
          <div className="relative h-7 w-11 shrink-0">
            <div className="absolute right-4 top-0 h-7 w-7 rounded-full bg-white/20" />
            <div className="absolute right-0 top-0 h-7 w-7 rounded-full bg-white/40" />
          </div>
        </div>

        <div className="flex items-end justify-between gap-3">
          <div className="min-w-0">
            {/* IC칩 — 접점을 나타내는 격자선을 넣어 실물 칩처럼 보이게 한다. */}
            <div className="relative h-7 w-9 rounded-[4px] bg-gradient-to-br from-yellow-200 via-yellow-400 to-yellow-600 mb-3">
              <div className="absolute inset-y-0 left-1/3 w-px bg-yellow-800/40" />
              <div className="absolute inset-y-0 left-2/3 w-px bg-yellow-800/40" />
              <div className="absolute inset-x-0 top-1/2 h-px bg-yellow-800/40" />
            </div>
            <p className="text-sm font-bold text-white truncate">{title}</p>
            {footer && (
              <p className="text-[10px] uppercase tracking-wide text-white/50 mt-0.5">{footer}</p>
            )}
          </div>
          {demoBadge}
        </div>
      </div>
    </div>
  );
}
