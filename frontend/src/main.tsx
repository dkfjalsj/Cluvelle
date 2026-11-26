import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
// 전역 스타일(Tailwind) 불러오기
import "./index.css";
import App from "./App.tsx";

// #root 요소에 앱을 StrictMode와 브라우저 라우터로 감싸 렌더링
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
