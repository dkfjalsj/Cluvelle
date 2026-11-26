import { toolLabel } from "../labels";
import type { EvidenceView } from "../types/api";

// 확보 증거 목록 속성
interface EvidenceListProps {
  // 확보한 증거 (중복 없음)
  items: EvidenceView[];
}

// 확보 증거 목록
// 지금까지 확보한 증거의 ID·도구·요약을 보여 주는 컴포넌트
export function EvidenceList({ items }: EvidenceListProps) {
  // 확보한 증거가 없을 때
  if (items.length === 0) {
    return <p className="text-sm text-slate-400">아직 확보한 증거가 없어요.</p>;
  }
  return (
    // 증거마다 한 줄
    <ul className="space-y-2 text-sm">
      {items.map((item) => (
        <li key={item.id} className="rounded-lg bg-slate-900 p-3">
          <p>
            <span className="font-mono text-sky-300">{item.id}</span>{" "}
            <span className="text-slate-400">
              ({toolLabel(item.source_tool)})
            </span>
          </p>
          <p className="mt-1 text-slate-200">{item.summary}</p>
        </li>
      ))}
    </ul>
  );
}
