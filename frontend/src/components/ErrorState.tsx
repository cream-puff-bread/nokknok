import type { ReactNode } from 'react';

import { Button } from './Button';

interface ErrorStateProps {
  // 오류 원문(스택, 서버 메시지)을 그대로 받지 않는다. 호출부가 이미
  // 사용자 안내 문구로 바꾼 message만 넘긴다(contracts/ui-system.md
  // "오류 원문 노출 금지").
  message: string;
  // 재시도가 의미 있는 오류(네트워크 오류, 일시적 서버 오류 등)에 쓴다.
  onRetry?: () => void;
  // 재시도가 소용없는 오류(예: 존재하지 않는 리소스로 딥링크된 경우)에 쓴다.
  // 이용자가 빠져나갈 다음 행동을 여기 담는다. EmptyState의 action과 같은
  // 슬롯 형태다.
  //
  // onRetry와 action이 둘 다 오면 action을 우선한다 — action이 왔다는 것
  // 자체가 "재시도로는 안 풀린다"는 더 구체적인 신호이기 때문이다.
  // 둘 다 없으면 메시지만 보여주고 버튼은 렌더링하지 않는다(EmptyState가
  // action 없이 메시지만 보여주는 것과 같은 규칙).
  action?: ReactNode;
}

export function ErrorState({ message, onRetry, action }: ErrorStateProps) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6 text-center space-y-4">
      <p className="text-sm text-gray-900">{message}</p>
      {action ?? (onRetry && (
        <Button variant="secondary" onClick={onRetry}>
          다시 시도
        </Button>
      ))}
    </div>
  );
}
