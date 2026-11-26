import { VERDICT_LABELS } from "../labels";
import type { GradingResult } from "../types/api";

// 채점 결과 보기 속성
interface GradingViewProps {
  // 채점 결과
  grading: GradingResult;
}

// 채점 결과 보기
// 판정·범인·결정적 증거별 확보·인용 여부·조사 횟수·최단 경로 길이·채점 메모를 보여 주는 컴포넌트
export function GradingView({ grading }: GradingViewProps) {
  return (
    <div className="rounded-lg border border-amber-700 bg-slate-900 p-4 text-sm">
      {/* 판정과 범인 */}
      <p className="text-lg font-semibold">
        판정: {VERDICT_LABELS[grading.verdict]}
      </p>
      <p className="mt-1 text-slate-200">
        범인: {grading.culprit_id} {grading.culprit_name}
      </p>
      {/* 결정적 증거별 확보·인용 */}
      <div className="mt-3">
        <p className="font-medium text-slate-300">결정적 증거</p>
        <ul className="mt-1 space-y-1">
          {grading.decisive_evidence_ids.map((evidenceId) => (
            <li key={evidenceId} className="text-slate-200">
              <span className="font-mono text-sky-300">{evidenceId}</span> 확보{" "}
              {grading.collected_decisive_ids.includes(evidenceId) ? "O" : "X"}{" "}
              · 인용{" "}
              {grading.cited_decisive_ids.includes(evidenceId) ? "O" : "X"}
            </li>
          ))}
        </ul>
      </div>
      {/* 조사 횟수와 최단 경로 */}
      <p className="mt-3 text-slate-300">
        조사 횟수 {grading.tool_call_count}회 · 최단 경로{" "}
        {grading.solution_path_length}회
      </p>
      {/* 채점 메모 */}
      <div className="mt-3">
        <p className="font-medium text-slate-300">채점 메모</p>
        <p className="leading-relaxed text-slate-200">
          {grading.grading_notes}
        </p>
      </div>
    </div>
  );
}
