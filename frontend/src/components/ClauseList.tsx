import type { ClauseRef } from '../types/contract';

interface ClauseListProps {
  clauses: ClauseRef[];
}

// 근거 조항 조회 실패 시 계약상 빈 배열이 온다(RouteOption.clauses).
// 그 상태에서 "근거 없음"이라고 확언하면, 실제로는 조인 실패일 뿐인데
// "이 카드는 근거가 없다"로 잘못 읽힐 수 있어 조용히 아무것도 안 그린다 —
// best 카드 자체(할인액 등)는 이미 표시돼 있으므로 화면이 빈 채로 남지 않는다.
export function ClauseList({ clauses }: ClauseListProps) {
  if (clauses.length === 0) return null;

  return (
    <div className="space-y-2">
      <h4 className="text-xs text-gray-500">근거 약관</h4>
      <ul className="space-y-2">
        {clauses.map((clause, i) => (
          <li key={i} className="bg-white rounded-lg border border-gray-200 p-4">
            <p className="text-sm text-gray-900">{clause.content}</p>
            <p className="text-xs text-gray-500 mt-2">
              {clause.docName} · {clause.pageNo}쪽
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
}
