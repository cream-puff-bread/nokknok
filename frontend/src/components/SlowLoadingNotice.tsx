import { useEffect, useState } from 'react';

/**
 * 오래 걸리는 요청에 "왜 기다리는지"를 알려준다.
 *
 * 무료 티어 콜드스타트를 실측하니 첫 요청이 32.6초, 첫 데이터 요청이 추가
 * 3.1초였다(CONTRIBUTING.md 시연 안정성). 화면 정적 자산은 CDN에서 즉시
 * 나오므로, 안내가 없으면 "화면은 떴는데 멈춘" 것처럼 보인다.
 */
const NOTICE_DELAY_MS = 6_000;

export function useSlowLoading(active: boolean): boolean {
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    if (!active) {
      setSlow(false);
      return;
    }
    const timer = setTimeout(() => setSlow(true), NOTICE_DELAY_MS);
    return () => clearTimeout(timer);
  }, [active]);

  return slow;
}

export function SlowLoadingNotice() {
  return (
    <p className="text-xs text-gray-500">
      서버를 깨우는 중입니다. 처음 접속하면 30초 정도 걸릴 수 있습니다.
    </p>
  );
}
