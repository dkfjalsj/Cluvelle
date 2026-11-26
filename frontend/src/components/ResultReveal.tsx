import { VERDICT_LABELS } from "../labels";
import type {
  GradingVerdict,
  InvestigationResult,
  PublicCase,
} from "../types/api";
import { UNKNOWN_PICK, type SuspectPick } from "../types/progress";
import { GradingView } from "./GradingView";
import { ReportView } from "./ReportView";
import { ResultMessage } from "./ResultMessage";

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

// AI 판정 카드
// 판정 값에 맞는 "AI 판정: 제목"과 설명 한 줄을 카드로 보여 주는 컴포넌트
function VerdictCard({ verdict }: { verdict: GradingVerdict }) {
  // 판정 문구
  const label = VERDICT_LABELS[verdict];
  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900 p-4">
      {/* 제목 */}
      <p className="font-semibold">AI 판정: {label.title}</p>
      {/* 설명 */}
      <p className="mt-1 text-sm text-slate-300">{label.description}</p>
    </div>
  );
}

// 결과 공개
// 결과 메시지·비교 카드·AI 판정·보고서·AI 수사 돌아보기를 보여 주고, AI 오류면 판정 카드와 내 선택·실제 범인만 보여 주는 컴포넌트
export function ResultReveal({
  pick,
  pickedAtStep,
  result,
  publicCase,
}: ResultRevealProps) {
  // 용의자 ID → 이름
  const suspectName = (id: string) =>
    publicCase?.suspects.find((item) => item.id === id)?.name;
  // 용의자 ID → "ID 이름"
  const suspectLabel = (id: string) => {
    const name = suspectName(id);
    return name ? `${id} ${name}` : id;
  };
  // 내 선택·AI 결론·실제 범인 표기
  const myPick = pick === UNKNOWN_PICK ? "모르겠어요" : suspectLabel(pick);
  const pickNote = `${pickedAtStep}단계에서 선택`;
  const report = result.final_report;
  const aiConclusion =
    report && report.verdict === "accuse" && report.suspect_id
      ? `${suspectName(report.suspect_id) ?? report.suspect_id} 지목`
      : "판단 보류";
  const grading = result.grading;
  const culprit = grading
    ? `${grading.culprit_id} ${grading.culprit_name}`
    : "";

  // AI 오류: 판정 카드와 내 선택·실제 범인만
  if (result.status === "failed") {
    return (
      <div className="space-y-4">
        <VerdictCard verdict="error" />
        <div className="grid gap-2 sm:grid-cols-2">
          <CompareCell title="내 선택" value={myPick} note={pickNote} />
          <CompareCell title="실제 범인" value={culprit} />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* 결과 메시지 카드 (맨 위) */}
      {grading && (
        <ResultMessage
          pick={pick}
          pickedAtStep={pickedAtStep}
          culpritId={grading.culprit_id}
          culpritName={grading.culprit_name}
          aiVerdict={grading.verdict}
        />
      )}
      {/* 비교 카드 3칸 */}
      <div className="grid gap-2 sm:grid-cols-3">
        <CompareCell title="내 선택" value={myPick} note={pickNote} />
        <CompareCell title="AI의 결론" value={aiConclusion} />
        <CompareCell title="실제 범인" value={culprit} />
      </div>
      {/* AI 판정 카드 */}
      {grading && <VerdictCard verdict={grading.verdict} />}
      {/* AI 보고서 전체 */}
      {report && (
        <ReportView
          report={report}
          reportStatus={result.report_status}
          publicCase={publicCase}
        />
      )}
      {/* AI 수사 돌아보기 */}
      {grading && <GradingView grading={grading} />}
    </div>
  );
}
