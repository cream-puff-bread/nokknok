import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // 개발 중에는 프록시로 백엔드를 같은 오리진처럼 다룬다.
    // 프론트가 상대경로 /api 로만 호출하면 백엔드 CORS_ORIGIN 설정이 어긋나도
    // 로컬 개발이 막히지 않는다. 배포 환경의 절대주소 주입 방식은 API 호출
    // 계층을 만들 때 함께 정한다(@fanfanduck).
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
});
