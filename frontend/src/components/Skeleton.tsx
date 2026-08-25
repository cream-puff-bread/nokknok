// contracts/ui-system.md 상태 처리 — 로딩: animate-pulse bg-gray-200 rounded 스켈레톤.
interface SkeletonProps {
  className?: string;
}

export function Skeleton({ className = 'h-4 w-full' }: SkeletonProps) {
  return <div className={`animate-pulse bg-gray-200 rounded ${className}`} />;
}
