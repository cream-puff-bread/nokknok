import type { ReactElement } from 'react';
import { Navigate, useNavigate, useParams } from 'react-router';

import { BalanceDashboardPage } from './pages/BalanceDashboardPage';
import { PersonaSelectPage } from './pages/PersonaSelectPage';
import { RouteResultPage } from './pages/RouteResultPage';
import { SimulationPage } from './pages/SimulationPage';
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
      onNavigateToPersonas={() => navigate('/personas')}
    />
  );
}

// TransactionUploadPage도 PersonaSelectRoute와 같은 이유로 래퍼를 둔다 —
// PERSONA_NOT_FOUND의 "페르소나 선택으로" 버튼이 풀 리로드 대신 SPA 전환을
// 쓰려면 useNavigate가 필요하고, 그걸 컴포넌트 안에 직접 넣지 않는다.
function TransactionUploadRoute() {
  const navigate = useNavigate();
  return <TransactionUploadPage onNavigateToPersonas={() => navigate('/personas')} />;
}

// URL 파라미터는 문자열이라 숫자로 바꾸는 곳이 필요하다. 화면이 직접 하면
// 라우팅을 알게 되므로 래퍼가 맡는다 — 화면은 personaId: number 만 받는다.
//
// 딥링크로 /balance/abc 처럼 숫자가 아닌 값이 들어올 수 있다. 그대로 넘기면
// NaN 이 쿼리에 실려 서버가 422 를 내는데, 이용자 입장에서는 주소가 잘못된
// 것이지 요청 값이 잘못된 게 아니다. 페르소나 선택으로 돌려보낸다.
// 형식이 틀린 personaId 는 여기서 걸러내고, 형식은 맞지만 존재하지 않는
// 페르소나(/balance/999)는 백엔드가 PERSONA_NOT_FOUND 로 알려준다. 후자의
// "페르소나 선택으로" 이동도 라우팅을 아는 이 계층이 맡는다.
function withPersonaId(
  render: (personaId: number, onNavigateToPersonas: () => void) => ReactElement,
): () => ReactElement {
  return function PersonaIdRoute() {
    const { personaId } = useParams();
    const navigate = useNavigate();
    const parsed = Number(personaId);
    if (!Number.isInteger(parsed) || parsed <= 0) {
      return <Navigate to="/personas" replace />;
    }
    return render(parsed, () => navigate('/personas'));
  };
}

const BalanceRoute = withPersonaId((personaId, onNavigateToPersonas) => (
  <BalanceDashboardPage
    personaId={personaId}
    onNavigateToPersonas={onNavigateToPersonas}
  />
));
const SimulateRoute = withPersonaId((personaId, onNavigateToPersonas) => (
  <SimulationPage personaId={personaId} onNavigateToPersonas={onNavigateToPersonas} />
));
const RouteResultRoute = withPersonaId((personaId, onNavigateToPersonas) => (
  <RouteResultPage personaId={personaId} onNavigateToPersonas={onNavigateToPersonas} />
));

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
  { path: '/upload/:personaId', element: <TransactionUploadRoute /> },

  { path: '/balance/:personaId', element: <BalanceRoute /> },
  { path: '/simulate/:personaId', element: <SimulateRoute /> },

  { path: '/route/:personaId', element: <RouteResultRoute /> },

  // 미매칭 경로 전부를 여기서 받는다(항상 배열 맨 끝에 둔다). SPA 폴백(#19)
  // 도입 이후로는 존재하지 않는 경로도 200으로 index.html을 받으므로,
  // 이 라우트가 없으면 /nope 같은 주소도 같은 빈 화면이 된다.
  { path: '*', element: <Navigate to="/personas" replace /> },
];
