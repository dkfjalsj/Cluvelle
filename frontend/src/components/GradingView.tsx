import type { GradingResult } from "../types/api";

// 채점 결과 보기 속성
interface GradingViewProps {
  // 채점 결과
  grading: GradingResult;
}

// 단서 상태 문구
// 결정적인 단서를 찾았는지와 보고서에 근거로 썼는지를 쉬운 말로 반환하는 함수
function clueStatus(found: boolean, cited: boolean): string {
  // 못 찾음 / 찾음 · 근거로 씀 / 찾음 · 근거로 안 씀
  if (!found) return "못 찾음";
  return cited ? "찾음 · 근거로 씀" : "찾음 · 근거로 안 씀";
}

// 채점 결과 보기
// 결정적인 단서별 찾음·근거 사용 여부, 조사 횟수와 가장 빠른 풀이 횟수, 사건 해설을 보여 주는 컴포넌트
export function GradingView({ grading }: GradingViewProps) {
  return (
    <div className="rounded-lg border border-amber-700 bg-slate-900 p-4 text-sm">
      {/* 제목 */}
      <p className="text-lg font-semibold">AI 수사 돌아보기</p>
      {/* 결정적인 단서별 상태 */}
      <div className="mt-3">
        <p className="font-medium text-slate-300">
          결정적인 단서 (범인을 확정하는 데 필요한 단서)
        </p>
        <ul className="mt-1 space-y-1">
          {grading.decisive_evidence_ids.map((evidenceId) => (
            <li key={evidenceId} className="text-slate-200">
              <span className="font-mono text-sky-300">{evidenceId}</span>{" "}
              {clueStatus(
                grading.collected_decisive_ids.includes(evidenceId),
                grading.cited_decisive_ids.includes(evidenceId),
              )}
            </li>
          ))}
        </ul>
      </div>
      {/* 조사 횟수와 가장 빠른 풀이 */}
      <p className="mt-3 text-slate-300">
        AI는 {grading.tool_call_count}번 조사했어요. 가장 빠른 풀이는{" "}
        {grading.solution_path_length}번이에요.
      </p>
      {/* 사건 해설 */}
      <div className="mt-3">
        <p className="font-medium text-slate-300">사건 해설</p>
        <p className="leading-relaxed text-slate-200">
          {grading.grading_notes}
        </p>
      </div>
    </div>
  );
}
