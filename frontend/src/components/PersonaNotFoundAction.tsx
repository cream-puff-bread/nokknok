import { Button } from './Button';

interface PersonaNotFoundActionProps {
  onNavigateToPersonas?: () => void;
}

// PERSONA_NOT_FOUND 오류의 공용 action 슬롯(ErrorState.action에 넣어 쓴다).
// onNavigateToPersonas가 있으면 라우터의 클라이언트 사이드 전환을 쓴다 —
// 콜드스타트가 30초 넘는 상황에서 풀 리로드는 그 대기를 처음부터 다시
// 겪게 만드는데, SPA 전환은 이미 받아둔 번들을 재사용한다.
//
// 콜백이 없으면(예: 페이지를 router 없이 단독 렌더링하는 경우) 일반 링크로
// 대체해 최소한 이동은 되게 한다 — 풀 리로드가 되긴 하지만 아예 갇히는
// 것보다는 낫다.
export function PersonaNotFoundAction({ onNavigateToPersonas }: PersonaNotFoundActionProps) {
  if (onNavigateToPersonas) {
    return (
      <Button variant="secondary" onClick={onNavigateToPersonas}>
        페르소나 선택으로
      </Button>
    );
  }
  return (
    <a
      href="/personas"
      className="bg-white hover:bg-gray-50 border border-gray-300 rounded-lg px-4 py-2 text-gray-700 text-sm font-medium transition-colors inline-block"
    >
      페르소나 선택으로
    </a>
  );
}
