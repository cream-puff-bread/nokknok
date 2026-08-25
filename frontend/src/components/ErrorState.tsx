import { Button } from './Button';

interface ErrorStateProps {
  // 오류 원문(스택, 서버 메시지)을 그대로 받지 않는다. 호출부가 이미
  // 사용자 안내 문구로 바꾼 message만 넘긴다(contracts/ui-system.md
  // "오류 원문 노출 금지").
  message: string;
  onRetry: () => void;
}

export function ErrorState({ message, onRetry }: ErrorStateProps) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6 text-center space-y-4">
      <p className="text-sm text-gray-900">{message}</p>
      <Button variant="secondary" onClick={onRetry}>
        다시 시도
      </Button>
    </div>
  );
}
