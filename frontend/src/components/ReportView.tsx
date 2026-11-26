import type { FinalReport, PublicCase } from "../types/api";

// 보고서 보기 속성
interface ReportViewProps {
  // 최종 보고서
  report: FinalReport;
  // 보고서 처리 결과 (forced_withhold면 강제 판단 보류)
  reportStatus: string | null;
  // 이름 표시용 공개 사건 정보
  publicCase: PublicCase | null;
}

// 목록 블록
// 제목과 문자열 목록을 보여 주고 비어 있으면 "없음"을 보여 주는 컴포넌트
function ListBlock({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="mt-3">
      {/* 제목 */}
      <p className="font-medium text-slate-300">{title}</p>
      {/* 항목 또는 없음 */}
      {items.length === 0 ? (
        <p className="text-slate-400">없음</p>
      ) : (
        <ul className="list-disc space-y-1 pl-5 text-slate-200">
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

// 최종 보고서 보기
// 결론(지목 또는 판단 보류)·인용 증거·불일치·미확인 사항·설명을 보여 주는 컴포넌트
export function ReportView({
  report,
  reportStatus,
  publicCase,
}: ReportViewProps) {
  // 지목한 용의자 표기 (ID + 이름)
  const suspectName = publicCase?.suspects.find(
    (item) => item.id === report.suspect_id,
  )?.name;
  const conclusion =
    report.verdict === "accuse"
      ? `지목: ${report.suspect_id ?? ""}${suspectName ? ` ${suspectName}` : ""}`
      : "판단 보류";
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900 p-4 text-sm">
      {/* 결론 */}
      <p className="text-lg font-semibold">{conclusion}</p>
      {reportStatus === "forced_withhold" && (
        <p className="mt-1 text-amber-300">
          보고서가 두 번 검증에 실패해 강제로 판단을 보류했어요.
        </p>
      )}
      {/* 인용 증거 */}
      <p className="mt-3 text-slate-300">
        인용 증거:{" "}
        <span className="font-mono text-sky-300">
          {report.cited_evidence_ids.join(", ") || "없음"}
        </span>
      </p>
      {/* 불일치·미확인 사항 */}
      <ListBlock title="발견한 불일치" items={report.contradictions} />
      <ListBlock title="확인하지 못한 사항" items={report.unverified} />
      {/* 설명 */}
      <div className="mt-3">
        <p className="font-medium text-slate-300">설명</p>
        <p className="leading-relaxed text-slate-200">{report.explanation}</p>
      </div>
    </div>
  );
}
