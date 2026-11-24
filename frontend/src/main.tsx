import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
// 전역 스타일(Tailwind) 불러오기
import "./index.css";
import App from "./App.tsx";

// #root 요소에 앱을 StrictMode로 렌더링
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
