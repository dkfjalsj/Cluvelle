import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  // React와 Tailwind CSS 플러그인 등록
  plugins: [react(), tailwindcss()],
  // 개발 서버 포트 5180 고정 (사용 중이면 다른 포트로 넘어가지 않고 종료)
  server: { port: 5180, strictPort: true },
});
