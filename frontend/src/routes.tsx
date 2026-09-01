import { useMemo, type ReactElement } from 'react';
import { Navigate, useNavigate, useParams, useSearchParams } from 'react-router';

import { AppLayout } from './components/AppLayout';
import type { ParsedQuery, PaymentType } from './types/contract';

const PAYMENT_TYPES: PaymentType[] = ['LUMP', 'INSTALLMENT', 'INTEREST_FREE'];
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
// 페르소나를 고른 다음 목적지는 업로드가 아니라 가용잔고다 — 업로드는
// 페르소나와 무관한 별개 진입점이라 아래 onNavigateToUpload로 따로 뺐다.
function PersonaSelectRoute() {
  const navigate = useNavigate();
  return (
    <AppLayout>
      <PersonaSelectPage
        onSelect={(persona) => navigate(`/balance/${persona.id}`)}
        onNavigateToPersonas={() => navigate('/personas')}
        onNavigateToUpload={() => navigate('/upload')}
      />
    </AppLayout>
  );
}

// TransactionUploadPage도 PersonaSelectRoute와 같은 이유로 래퍼를 둔다 —
// PERSONA_NOT_FOUND의 "페르소나 선택으로" 버튼이 풀 리로드 대신 SPA 전환을
// 쓰려면 useNavigate가 필요하고, 그걸 컴포넌트 안에 직접 넣지 않는다.
//
// 업로드는 personaId를 쓰지 않는다(컴포넌트가 useParams를 읽지 않음) — URL도
// 그 사실을 반영해 /upload 하나로 둔다. personaId 종속 화면이 아니므로
// AppLayout에도 personaId를 넘기지 않아 탭이 뜨지 않는다.
function TransactionUploadRoute() {
  const navigate = useNavigate();
  return (
    <AppLayout>
      <TransactionUploadPage onNavigateToPersonas={() => navigate('/personas')} />
    </AppLayout>
  );
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
    return <AppLayout personaId={parsed}>{render(parsed, () => navigate('/personas'))}</AppLayout>;
  };
}

const BalanceRoute = withPersonaId((personaId, onNavigateToPersonas) => (
  <BalanceDashboardPage
    personaId={personaId}
    onNavigateToPersonas={onNavigateToPersonas}
  />
));
// 결제 라우팅에서 넘어온 구매는 URL 쿼리로 싣는다. 공유 상태를 쓰면 새로고침과
// 딥링크에서 사라지는데, personaId 를 URL 에 두기로 한 것과 같은 이유로 주소에
// 남긴다. 값이 하나라도 모자라거나 형식이 틀리면 그냥 무시하고 평소의 자연어
// 입력 화면을 보여준다 — 잘못된 주소 때문에 화면이 막히지 않게 한다.
function useIncomingPurchase(): ParsedQuery | undefined {
  const [params] = useSearchParams();
  const amount = Number(params.get('amount'));
  const months = Number(params.get('installmentMonths') ?? '0');
  const category = params.get('category');
  const paymentType = params.get('paymentType');

  return useMemo(() => {
    if (!Number.isInteger(amount) || amount <= 0) return undefined;
    if (!category || !paymentType) return undefined;
    if (!PAYMENT_TYPES.includes(paymentType as PaymentType)) return undefined;
    if (!Number.isInteger(months) || months < 0) return undefined;
    return {
      amount,
      category,
      paymentType: paymentType as PaymentType,
      installmentMonths: months,
    };
    // params 객체는 렌더마다 새 참조라 원시값으로 의존성을 건다.
  }, [amount, category, paymentType, months]);
}

const SimulateRoute = withPersonaId((personaId, onNavigateToPersonas) => (
  <SimulateScreen personaId={personaId} onNavigateToPersonas={onNavigateToPersonas} />
));

function SimulateScreen({
  personaId,
  onNavigateToPersonas,
}: {
  personaId: number;
  onNavigateToPersonas: () => void;
}) {
  return (
    <SimulationPage
      personaId={personaId}
      onNavigateToPersonas={onNavigateToPersonas}
      incomingPurchase={useIncomingPurchase()}
    />
  );
}

const RouteResultRoute = withPersonaId((personaId, onNavigateToPersonas) => (
  <RouteResultScreen personaId={personaId} onNavigateToPersonas={onNavigateToPersonas} />
));

// 라우팅 결과 -> 시뮬레이션 이동. 화면은 값만 넘기고 어디로 갈지는 모른다
// (PersonaSelectRoute 와 같은 이유로 래퍼가 useNavigate 를 맡는다).
function RouteResultScreen({
  personaId,
  onNavigateToPersonas,
}: {
  personaId: number;
  onNavigateToPersonas: () => void;
}) {
  const navigate = useNavigate();
  return (
    <RouteResultPage
      personaId={personaId}
      onNavigateToPersonas={onNavigateToPersonas}
      onSimulate={(purchase) =>
        navigate({
          pathname: `/simulate/${personaId}`,
          search: new URLSearchParams({
            amount: String(purchase.amount),
            category: purchase.category,
            paymentType: purchase.paymentType,
            installmentMonths: String(purchase.installmentMonths),
          }).toString(),
        })
      }
    />
  );
}

// 다음 사람은 이 배열 맨 끝에 한 줄만 추가한다. 같은 지점에 동시에 삽입하면
// 병합 충돌이 나기 쉬우므로, 배열 중간에 끼워 넣지 않는다.
//
// 새 라우트는 element 를 <AppLayout> 으로 감싼다. personaId 종속 화면이면
// <AppLayout personaId={...}> 로 넘겨 탭이 뜨게 한다.
export const routes: RouteEntry[] = [
  // <Routes>는 매칭이 없으면 null을 렌더링한다. 배포 루트(/)가 그 상태로
  // 나가면 헤더만 뜨고 본문이 빈다 — 심사위원이 맨 처음 여는 주소다.
  // replace를 써서 뒤로가기에서 / ↔ /personas 루프가 안 생기게 한다.
  { path: '/', element: <Navigate to="/personas" replace /> },
  { path: '/personas', element: <PersonaSelectRoute /> },
  // 업로드는 페르소나와 무관한 별개 진입점이다(위 PersonaSelectRoute 주석
  // 참고) — personaId를 URL에 싣지 않는다.
  { path: '/upload', element: <TransactionUploadRoute /> },

  { path: '/balance/:personaId', element: <BalanceRoute /> },
  { path: '/simulate/:personaId', element: <SimulateRoute /> },

  { path: '/route/:personaId', element: <RouteResultRoute /> },

  // 미매칭 경로 전부를 여기서 받는다(항상 배열 맨 끝에 둔다). SPA 폴백(#19)
  // 도입 이후로는 존재하지 않는 경로도 200으로 index.html을 받으므로,
  // 이 라우트가 없으면 /nope 같은 주소도 같은 빈 화면이 된다.
  { path: '*', element: <Navigate to="/personas" replace /> },
];
