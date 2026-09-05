/**
 * 넉넉 로고 — 마크와 워드마크.
 *
 * 마크는 디자인으로 받은 지갑 그림(`public/logo-mark.png`)이다. 원본은
 * 2000x2000, 654KB 라 그대로 쓰지 않는다 — 여백을 잘라 내고 정사각으로 맞춘
 * 뒤 256px 로 줄여 둔다. 헤더에서는 32px 로 그리므로 고해상도 화면까지
 * 감당하고도 남는다. 만드는 법은 public/README.md 에 있다.
 *
 * SVG 가 아니라 래스터라 currentColor 로 물들일 수 없다. 다행히 마크가 중간
 * 톤 파랑이라 밝은 배경과 어두운 배경 양쪽에서 그대로 읽힌다 — 배경에 따라
 * 색을 바꿔야 하는 자리에는 쓰지 않는다.
 */

interface LogoProps {
  /** 워드마크를 함께 그릴지. 좁은 자리에서는 마크만 쓴다. */
  withWordmark?: boolean;
  className?: string;
}

export function Logo({ withWordmark = true, className = '' }: LogoProps) {
  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      <LogoMark className="h-8 w-8 shrink-0" />
      {withWordmark && (
        <span className="font-wordmark text-2xl font-bold tracking-tight text-gray-900">
          넉넉
        </span>
      )}
    </span>
  );
}

export function LogoMark({ className = '' }: { className?: string }) {
  return (
    // 로고 옆에 늘 "넉넉" 글자가 붙으므로 마크는 장식으로 둔다. alt 를 채우면
    // 읽는 장치가 서비스명을 두 번 말한다.
    <img src="/logo-mark.png" alt="" aria-hidden className={`object-contain ${className}`} />
  );
}
