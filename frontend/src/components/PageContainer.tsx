import type { ReactNode } from "react";
import { Link } from "react-router";

import { Logo } from "./Logo";

// 페이지 틀 속성
interface PageContainerProps {
  // 페이지 내용
  children: ReactNode;
  // 넓은 화면에서 2열 배치를 위해 폭을 넓힐지 여부
  wide?: boolean;
}

// 페이지 틀
// 어두운 배경 위에 로고 머리글과 가운데 정렬된 본문을 그리는 컴포넌트
export function PageContainer({ children, wide = false }: PageContainerProps) {
  // 본문 최대 폭 (기본 약 768px, 넓은 화면용은 더 넓게)
  const widthClass = wide ? "max-w-3xl lg:max-w-6xl" : "max-w-3xl";
  return (
    // 전체 화면 어두운 배경 (가로 넘침 방지)
    <div className="min-h-screen overflow-x-hidden bg-slate-950 text-slate-100">
      {/* 머리글: 로고 + 앱 이름, 누르면 사건 목록 */}
      <header className="border-b border-slate-800">
        <div className={`mx-auto w-full ${widthClass} px-4 py-3`}>
          <Link
            to="/"
            className="inline-flex min-h-11 items-center gap-2 text-lg font-bold"
          >
            <Logo />
            Cluvelle
          </Link>
        </div>
      </header>
      {/* 가운데 정렬 본문 */}
      <main className={`mx-auto w-full ${widthClass} px-4 py-6 break-words`}>
        {children}
      </main>
    </div>
  );
}
