import { toolLabel } from "../labels";
import type {
  EvidenceFoundData,
  PublicCase,
  ToolSelectedData,
} from "../types/api";

// 타임라인 단계
// 한 순번의 도구 선택·가설 변경·결과를 묶은 타입
export interface TimelineStep {
  // 순번
  step: number;
  // 도구 선택 이벤트 데이터
  selected?: ToolSelectedData;
  // 이 단계에서 바뀐 가설
  hypothesis?: string;
  // 결과 이벤트 데이터 (아직 없으면 조사 중)
  found?: EvidenceFoundData;
}

// 타임라인 항목 속성
interface TimelineItemProps {
  // 표시할 단계
  item: TimelineStep;
  // 이름 표시용 공개 사건 정보 (없으면 ID로 표시)
  publicCase: PublicCase | null;
}

// 인자 문자열 꺼내기
// 도구 인자에서 지정한 키의 값을 문자열로 꺼내는 함수 (없으면 빈 문자열)
function argText(args: Record<string, unknown>, key: string): string {
  // 값이 있으면 문자열로
  const value = args[key];
  return value === undefined || value === null ? "" : String(value);
}

// 조사 대상 문장
// 도구와 인자로 "장소: 실험실", "S3 정민혁 · 주제: ..." 같은 대상 문장을 만드는 함수
function describeTarget(
  tool: string,
  args: Record<string, unknown>,
  publicCase: PublicCase | null,
): string {
  // ID → 이름 조회
  const locationName = (id: string) =>
    publicCase?.locations.find((item) => item.id === id)?.name ?? id;
  const suspectLabel = (id: string) => {
    const name = publicCase?.suspects.find((item) => item.id === id)?.name;
    return name ? `${id} ${name}` : id;
  };
  const topicName = (id: string) =>
    publicCase?.topics.find((item) => item.id === id)?.name ?? id;
  const cameraLabel = (id: string) => {
    const name = publicCase?.cameras.find((item) => item.id === id)?.name;
    return name ? `${id} ${name}` : id;
  };
  // 도구별 대상 문장
  switch (tool) {
    case "inspect_scene":
      return `장소: ${locationName(argText(args, "location_id"))}`;
    case "interview_suspect":
      return `${suspectLabel(argText(args, "suspect_id"))} · 주제: ${topicName(argText(args, "topic_id"))}`;
    case "check_cctv":
      return `${cameraLabel(argText(args, "camera_id"))} · ${argText(args, "time_window")}`;
    case "verify_alibi":
      return suspectLabel(argText(args, "suspect_id"));
    case "cross_check_evidence": {
      const ids = Array.isArray(args.evidence_ids)
        ? args.evidence_ids.map(String)
        : [];
      return `증거: ${ids.join(", ")}`;
    }
    default:
      // 알 수 없는 도구는 인자 그대로
      return JSON.stringify(args);
  }
}

// 타임라인 항목
// 한 단계의 도구·대상·고른 이유·그때의 가설·결과(또는 조사 중)를 보여 주는 컴포넌트
export function TimelineItem({ item, publicCase }: TimelineItemProps) {
  // 도구 이름과 결과
  const tool = item.selected?.tool ?? item.found?.tool ?? "";
  const found = item.found;
  return (
    <li className="rounded-lg border border-slate-800 bg-slate-900 p-3 text-sm">
      {/* 순번·도구·대상 */}
      <p className="font-medium">
        <span className="text-slate-400">{item.step}.</span> {toolLabel(tool)}
      </p>
      {item.selected && (
        <p className="mt-1 text-slate-200">
          {describeTarget(tool, item.selected.args, publicCase)}
        </p>
      )}
      {/* 이 조사를 고른 이유 */}
      {item.selected?.reason && (
        <p className="mt-1 text-slate-400">
          이 조사를 고른 이유: {item.selected.reason}
        </p>
      )}
      {/* 이때의 가설 (바뀌지 않았으면 가설 변화 없음) */}
      <p className="mt-1 text-amber-300">
        이때의 가설: {item.hypothesis ?? "가설 변화 없음"}
      </p>
      {/* 결과 */}
      <div className="mt-2">
        {!found && <p className="text-slate-400">조사 중...</p>}
        {found?.error && <p className="text-red-400">오류: {found.error}</p>}
        {found && !found.error && found.evidence.length > 0 && (
          <ul className="space-y-1">
            {found.evidence.map((evidence) => (
              <li key={evidence.id} className="text-slate-200">
                <span className="font-mono text-sky-300">{evidence.id}</span>{" "}
                {evidence.summary}
              </li>
            ))}
          </ul>
        )}
        {found && !found.error && found.evidence.length === 0 && (
          <p className="text-slate-400">
            {found.found === null ? "교차 검증 완료" : "특이사항 없음"}
          </p>
        )}
      </div>
    </li>
  );
}
