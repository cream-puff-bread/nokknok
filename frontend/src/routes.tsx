import type { ReactElement } from 'react';
import { useNavigate } from 'react-router';

import { PersonaSelectPage } from './pages/PersonaSelectPage';
import { TransactionUploadPage } from './pages/TransactionUploadPage';

export interface RouteEntry {
  path: string;
  element: ReactElement;
}

// PersonaSelectPage는 onSelect 콜백 prop을 받을 뿐 라우팅을 모른다(컴포넌트를
// router에 결합하지 않기 위해서다). "선택 후 다음 화면으로 이동"은 이 래퍼가
// useNavigate로 담당한다.
//
// personaId를 다음 화면에 어떻게 넘길지(URL 파라미터 vs 공유 상태)는 아직
// 팀 합의 전이다 — 일단 URL 파라미터로 둔다. 합의되면 이 래퍼만 고치면 된다.
function PersonaSelectRoute() {
  const navigate = useNavigate();
  return (
    <PersonaSelectPage
      onSelect={(persona) => navigate(`/upload/${persona.id}`)}
    />
  );
}

// 다음 사람은 이 배열 맨 끝에 한 줄만 추가한다. 같은 지점에 동시에 삽입하면
// 병합 충돌이 나기 쉬우므로, 배열 중간에 끼워 넣지 않는다.
export const routes: RouteEntry[] = [
  { path: '/personas', element: <PersonaSelectRoute /> },
  // TransactionUploadPage는 아직 :personaId를 읽지 않는다(팀 합의 대기 —
  // 위 PersonaSelectRoute 주석 참고). URL에는 실려 있으니, 합의되면
  // useParams로 꺼내 쓰면 된다.
  { path: '/upload/:personaId', element: <TransactionUploadPage /> },

  // 아래는 팀원 담당 화면 자리 — 각자 여기에 한 줄씩 추가한다.
  // { path: '/route', element: <RouteResultPage /> },      // @seohee-P: 결제 라우팅 결과, 근거 약관 표시
  // { path: '/balance', element: <BalanceDashboardPage /> }, // @fanfanduck: 가용잔고 대시보드
  // { path: '/simulate', element: <SimulationPage /> },      // @fanfanduck: 시뮬레이션 입력, 잔고 추이 차트
];
