// 안내문 속성
interface GuidePanelProps {
  // 처음 보는 안내문인지 (처음이면 "시작하기", 다시 열면 "닫기")
  firstTime: boolean;
  // 닫기 처리
  onClose: () => void;
}

// 안내문 문장
const GUIDE_LINES = [
  "AI 탐정이 스스로 조사할 곳을 골라 수사해요. 조사할 때마다 예산 1회를 쓰고, 최대 10회까지 조사해요.",
  '"다음"을 눌러 AI의 조사를 한 단계씩 확인하세요. 조사 결과와 AI가 그때 세운 가설을 볼 수 있어요.',
  '범인을 알 것 같으면 언제든 "범인 고르기"를 누르세요. 끝까지 본 뒤에 골라도 돼요.',
  "범인을 고르면 AI의 결론과 정답을 함께 보여 드려요.",
];

// 진행 방식 안내문
// 수사 화면의 진행 방식을 안내하고 시작하기(또는 닫기) 버튼으로 닫는 컴포넌트
export function GuidePanel({ firstTime, onClose }: GuidePanelProps) {
  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900 p-4 text-sm">
      {/* 안내 문장 목록 */}
      <ul className="list-disc space-y-2 pl-5 leading-relaxed text-slate-200">
        {GUIDE_LINES.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
      {/* 닫기 버튼 */}
      <button
        type="button"
        onClick={onClose}
        className="mt-4 min-h-11 w-full rounded-lg bg-sky-600 px-4 font-semibold hover:bg-sky-500"
      >
        {firstTime ? "시작하기" : "닫기"}
      </button>
    </div>
  );
}
