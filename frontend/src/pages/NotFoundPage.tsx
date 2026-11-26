import { Link } from "react-router";

import { PageContainer } from "../components/PageContainer";

// 페이지 없음 화면
// 없는 주소일 때 안내와 사건 목록으로 가는 링크를 보여 주는 컴포넌트
export function NotFoundPage() {
  return (
    <PageContainer>
      {/* 안내 */}
      <h1 className="text-xl font-bold">페이지를 찾을 수 없어요.</h1>
      {/* 목록 링크 */}
      <Link to="/" className="mt-4 inline-block text-sky-400 underline">
        사건 목록으로
      </Link>
    </PageContainer>
  );
}
