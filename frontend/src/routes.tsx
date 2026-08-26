import type { ReactElement } from 'react';
import { Navigate, useNavigate } from 'react-router';

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
  // <Routes>는 매칭이 없으면 null을 렌더링한다. 배포 루트(/)가 그 상태로
  // 나가면 헤더만 뜨고 본문이 빈다 — 심사위원이 맨 처음 여는 주소다.
  // replace를 써서 뒤로가기에서 / ↔ /personas 루프가 안 생기게 한다.
  { path: '/', element: <Navigate to="/personas" replace /> },
  { path: '/personas', element: <PersonaSelectRoute /> },
  // TransactionUploadPage는 아직 :personaId를 읽지 않는다(팀 합의 대기 —
  // 위 PersonaSelectRoute 주석 참고). URL에는 실려 있으니, 합의되면
  // useParams로 꺼내 쓰면 된다.
  { path: '/upload/:personaId', element: <TransactionUploadPage /> },

  // 아래는 팀원 담당 화면 자리 — 각자 여기에 한 줄씩 추가한다.
  // { path: '/route', element: <RouteResultPage /> },      // @seohee-P: 결제 라우팅 결과, 근거 약관 표시
  // { path: '/balance', element: <BalanceDashboardPage /> }, // @fanfanduck: 가용잔고 대시보드
  // { path: '/simulate', element: <SimulationPage /> },      // @fanfanduck: 시뮬레이션 입력, 잔고 추이 차트

  // 미매칭 경로 전부를 여기서 받는다(항상 배열 맨 끝에 둔다). SPA 폴백(#19)
  // 도입 이후로는 존재하지 않는 경로도 200으로 index.html을 받으므로,
  // 이 라우트가 없으면 /nope 같은 주소도 같은 빈 화면이 된다.
  { path: '*', element: <Navigate to="/personas" replace /> },
];
