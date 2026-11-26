import { VERDICT_LABELS } from "../labels";
import type { InvestigationResult, PublicCase } from "../types/api";
import { UNKNOWN_PICK, type SuspectPick } from "../types/progress";
import { GradingView } from "./GradingView";
import { ReportView } from "./ReportView";

// 결과 공개 속성
interface ResultRevealProps {
  // 사용자가 고른 값
  pick: SuspectPick;
  // 고른 시점의 공개 단계 수
  pickedAtStep: number;
  // 종료된 수사 결과 (보고서·채점 포함)
  result: InvestigationResult;
  // 이름 표시용 공개 사건 정보
  publicCase: PublicCase | null;
}

// 비교 칸
// 제목과 값을 담은 비교 카드 한 칸을 그리는 컴포넌트
function CompareCell({
  title,
  value,
  note,
}: {
  title: string;
  value: string;
  note?: string;
}) {
  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900 p-3">
      {/* 칸 제목과 값 */}
      <p className="text-xs text-slate-400">{title}</p>
      <p className="mt-1 font-semibold">{value}</p>
      {note && <p className="mt-1 text-xs text-slate-400">{note}</p>}
    </div>
  );
}

// 결과 공개
// 내 선택·AI의 결론·실제 범인 비교, 내 결과 문구, AI 채점 판정·보고서·채점 상세를 보여 주는 컴포넌트
export function ResultReveal({
  pick,
  pickedAtStep,
  result,
  publicCase,
}: ResultRevealProps) {
  // 용의자 ID → "ID 이름"
  const suspectLabel = (id: string) => {
    const name = publicCase?.suspects.find((item) => item.id === id)?.name;
    return name ? `${id} ${name}` : id;
  };
  // 내 선택·AI 결론·실제 범인 표기
  const myPick = pick === UNKNOWN_PICK ? "모르겠어요" : suspectLabel(pick);
  const report = result.final_report;
  const aiConclusion =
    report && report.verdict === "accuse" && report.suspect_id
      ? suspectLabel(report.suspect_id)
      : "판단 보류";
  const grading = result.grading;
  const culprit = grading
    ? `${grading.culprit_id} ${grading.culprit_name}`
    : "";
  // 내 결과 문구
  const myResult =
    pick === UNKNOWN_PICK
      ? '"모르겠어요"를 선택했어요'
      : grading && pick === grading.culprit_id
        ? "맞혔어요"
        : "틀렸어요";

  return (
    <div className="space-y-4">
      {/* 비교 카드 3칸 */}
      <div className="grid gap-2 sm:grid-cols-3">
        <CompareCell
          title="내 선택"
          value={myPick}
          note={`${pickedAtStep}단계에서 선택`}
        />
        <CompareCell title="AI의 결론" value={aiConclusion} />
        <CompareCell title="실제 범인" value={culprit} />
      </div>
      {/* 내 결과 */}
      <p className="text-lg font-bold text-amber-300">{myResult}</p>
      {/* AI 채점 판정 */}
      {grading && (
        <p className="text-sm text-slate-200">
          AI 채점 판정:{" "}
          <span className="font-semibold">
            {VERDICT_LABELS[grading.verdict]}
          </span>
        </p>
      )}
      {/* AI 보고서 전체 */}
      {report && (
        <ReportView
          report={report}
          reportStatus={result.report_status}
          publicCase={publicCase}
        />
      )}
      {/* 채점 상세 */}
      {grading && <GradingView grading={grading} />}
    </div>
  );
}
