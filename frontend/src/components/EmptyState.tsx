import type { ReactNode } from 'react';

interface EmptyStateProps {
  message: string;
  action?: ReactNode;
}

// contracts/ui-system.md 상태 처리 — 빈 값: 안내 문구 + 다음 행동 유도.
export function EmptyState({ message, action }: EmptyStateProps) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6 text-center space-y-4">
      <p className="text-sm text-gray-500">{message}</p>
      {action}
    </div>
  );
}
