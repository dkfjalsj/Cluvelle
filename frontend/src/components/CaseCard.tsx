import { Link } from "react-router";

import { DIFFICULTY_LABELS } from "../labels";
import type { CaseListItem } from "../types/api";

// 사건 카드 속성
interface CaseCardProps {
  // 표시할 사건 요약
  item: CaseListItem;
}

// 사건 카드
// 사건 제목·난이도·한 줄 소개·조사 예산을 보여 주고 누르면 사건 상세로 가는 컴포넌트
export function CaseCard({ item }: CaseCardProps) {
  return (
    // 카드 전체가 사건 상세 링크
    <Link
      to={`/cases/${item.case_id}`}
      className="block rounded-lg border border-slate-800 bg-slate-900 p-4 hover:border-slate-600"
    >
      {/* 제목과 난이도 */}
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-lg font-semibold">{item.title}</h2>
        <span className="rounded bg-slate-800 px-2 py-0.5 text-xs text-slate-300">
          {DIFFICULTY_LABELS[item.difficulty]}
        </span>
      </div>
      {/* 한 줄 소개 */}
      <p className="mt-2 text-sm text-slate-300">{item.summary}</p>
      {/* 조사 예산 */}
      <p className="mt-2 text-xs text-slate-400">
        조사 예산 {item.tool_budget}회
      </p>
    </Link>
  );
}
