import type { ReactNode } from "react";

// 페이지 틀 속성
interface PageContainerProps {
  // 페이지 내용
  children: ReactNode;
}

// 페이지 틀
// 어두운 배경 위에 가운데 정렬된 단일 열(최대 폭 약 768px)로 내용을 감싸는 컴포넌트
export function PageContainer({ children }: PageContainerProps) {
  return (
    // 전체 화면 어두운 배경 (가로 넘침 방지)
    <div className="min-h-screen overflow-x-hidden bg-slate-950 text-slate-100">
      {/* 가운데 정렬 단일 열 */}
      <main className="mx-auto w-full max-w-3xl px-4 py-8 break-words">
        {children}
      </main>
    </div>
  );
}
