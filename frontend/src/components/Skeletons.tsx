// 회색 막대
// 지정한 크기 클래스로 회색 자리표시 상자를 그리는 컴포넌트
function Bar({ className }: { className: string }) {
  // 회색 둥근 상자
  return <div className={`rounded bg-slate-800 ${className}`} />;
}

// 사건 목록 스켈레톤
// 사건 목록을 불러오는 동안 회색 카드 4개를 보여 주는 컴포넌트
export function CaseListSkeleton() {
  return (
    // 모바일 1열, PC 2열 회색 카드
    <ul className="grid gap-3 lg:grid-cols-2" aria-hidden="true">
      {[0, 1, 2, 3].map((index) => (
        <li key={index} className="rounded-lg bg-slate-900 p-4">
          <Bar className="h-5 w-2/3" />
          <Bar className="mt-3 h-4 w-full" />
          <Bar className="mt-2 h-3 w-1/3" />
        </li>
      ))}
    </ul>
  );
}

// 사건 상세 스켈레톤
// 사건 정보를 불러오는 동안 제목 막대·문단 막대 3줄·상자 2개를 보여 주는 컴포넌트
export function CaseDetailSkeleton() {
  return (
    <div aria-hidden="true">
      {/* 제목 막대 */}
      <Bar className="mt-4 h-7 w-1/2" />
      {/* 문단 막대 3줄 */}
      <Bar className="mt-4 h-4 w-full" />
      <Bar className="mt-2 h-4 w-full" />
      <Bar className="mt-2 h-4 w-3/4" />
      {/* 상자 2개 */}
      <Bar className="mt-6 h-20 w-full" />
      <Bar className="mt-3 h-20 w-full" />
    </div>
  );
}
