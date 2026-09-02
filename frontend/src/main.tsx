import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router';

import App from './App';
import './index.css';
import { ThemeProvider } from './theme/ThemeProvider';

const container = document.getElementById('root');
if (!container) {
  throw new Error('#root 엘리먼트를 찾을 수 없습니다. index.html 을 확인하세요.');
}

createRoot(container).render(
  <StrictMode>
    <ThemeProvider>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </ThemeProvider>
  </StrictMode>,
);
