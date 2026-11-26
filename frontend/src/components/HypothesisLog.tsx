import type { TimelineStep } from "./TimelineItem";

// 가설 기록 속성
interface HypothesisLogProps {
  // 공개된 단계 (순번 오름차순)
  steps: TimelineStep[];
}

// 가설 기록
// 공개된 단계 중 가설이 바뀐 단계를 "n단계 · 가설" 형식으로 순서대로 보여 주고, 없으면 안내 문구를 보여 주는 컴포넌트
export function HypothesisLog({ steps }: HypothesisLogProps) {
  // 가설이 바뀐 단계만
  const entries = steps.filter((item) => item.hypothesis);
  return (
    <section>
      {/* 제목 */}
      <h2 className="text-lg font-semibold">가설 기록</h2>
      {entries.length === 0 ? (
        // 빈 상태 안내
        <p className="mt-2 text-sm text-slate-400">
          아직 가설 기록이 없어요. &apos;다음&apos;을 눌러 첫 조사를 확인해
          보세요.
        </p>
      ) : (
        // 단계별 가설
        <ol className="mt-2 space-y-1 text-sm text-amber-200">
          {entries.map((item) => (
            <li key={item.step}>
              {item.step}단계 · {item.hypothesis}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
