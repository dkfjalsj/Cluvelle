import { Route, Routes } from "react-router";

import { CaseDetailPage } from "./pages/CaseDetailPage";
import { CaseListPage } from "./pages/CaseListPage";
import { InvestigationPage } from "./pages/InvestigationPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { ResultPage } from "./pages/ResultPage";

// 앱 루트
// 주소에 따라 사건 목록·사건 상세·수사 화면·결과 화면·페이지 없음을 보여 주는 최상위 컴포넌트
function App() {
  return (
    // 경로별 화면
    <Routes>
      <Route path="/" element={<CaseListPage />} />
      <Route path="/cases/:caseId" element={<CaseDetailPage />} />
      <Route
        path="/investigations/:investigationId"
        element={<InvestigationPage />}
      />
      <Route
        path="/investigations/:investigationId/result"
        element={<ResultPage />}
      />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}

export default App;
