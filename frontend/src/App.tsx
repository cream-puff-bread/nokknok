import { Route, Routes } from 'react-router';

import { routes } from './routes';

export default function App() {
  return (
    // 헤더·탭은 src/components/AppLayout.tsx가 담당한다. 화면별로 personaId
    // 유무가 다르므로(탭 노출 여부) 레이아웃은 여기서 한 번에 감싸지 않고
    // routes.tsx의 각 라우트 래퍼가 개별적으로 씌운다.
    <Routes>
      {routes.map(({ path, element }) => (
        <Route key={path} path={path} element={element} />
      ))}
    </Routes>
  );
}
