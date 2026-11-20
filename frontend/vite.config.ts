import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// React와 Tailwind CSS 플러그인 등록
export default defineConfig({
  plugins: [react(), tailwindcss()],
});
