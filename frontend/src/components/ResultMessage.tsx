import type { GradingVerdict } from "../types/api";
import { UNKNOWN_PICK, type SuspectPick } from "../types/progress";

// 결과 메시지 속성
interface ResultMessageProps {
  // 사용자가 고른 값
  pick: SuspectPick;
  // 고른 시점의 공개 단계 수
  pickedAtStep: number;
  // AI 수사관이 실제로 조사한 횟수
  aiToolCallCount: number;
  // 실제 범인 ID
  culpritId: string;
  // 실제 범인 이름
  culpritName: string;
  // AI 채점 판정
  aiVerdict: GradingVerdict;
}

// 한글 음절 범위 (가~힣)
const HANGUL_START = 0xac00;
const HANGUL_END = 0xd7a3;

// 받침 여부
// 마지막 글자가 한글이면 받침이 있는지(true/false), 한글이 아니면 null을 반환하는 함수
function hasFinalConsonant(word: string): boolean | null {
  // 마지막 글자 코드
  const last = word.trim().slice(-1);
  if (!last) return null;
  const code = last.charCodeAt(0);
  // 한글 음절이 아니면 판단 불가
  if (code < HANGUL_START || code > HANGUL_END) return null;
  // 종성 번호가 0이 아니면 받침 있음
  return (code - HANGUL_START) % 28 !== 0;
}

// 목적격 조사 붙이기
// 이름 뒤에 받침에 맞는 "을/를"을 붙이고, 한글이 아니면 "을(를)"을 붙이는 함수
function withObjectParticle(word: string): string {
  // 받침 여부에 따라 조사 선택
  const final = hasFinalConsonant(word);
  if (final === null) return `${word}을(를)`;
  return `${word}${final ? "을" : "를"}`;
}

// 과거형 서술 붙이기
// 이름 뒤에 받침에 맞는 "이었어요/였어요"를 붙이고, 한글이 아니면 "이었어요"를 붙이는 함수
function withWasEnding(word: string): string {
  // 받침이 없을 때만 "였어요"
  const final = hasFinalConsonant(word);
  return `${word}${final === false ? "였어요" : "이었어요"}`;
}

// 맞힌 경우 제목
// 범인을 고른 시점의 공개 단계 수(n)를 AI 수사관의 조사 횟수(T)와 비교해 축하 제목을 반환하는 함수
function correctTitle(steps: number, aiCalls: number): string {
  // 단서를 보기 전 / AI 수사관보다 먼저 / 끝까지 함께
  if (steps === 0)
    return "🎉 단서를 보기도 전에 범인을 맞혔어요! 직감이 대단해요.";
  if (steps < aiCalls)
    return `🎉 AI 수사관보다 먼저, ${steps}단계 만에 범인을 찾아냈어요!`;
  return "🎉 AI 수사관과 함께 끝까지 단서를 따라가 범인을 맞혔어요!";
}

// AI 수사관 비교 문구
// AI 수사관의 판정과 조사 횟수에 맞춰 AI 수사관 결과와 비교한 한 줄을 반환하는 함수 (오류면 null)
function aiComparison(
  verdict: GradingVerdict,
  culpritName: string,
  steps: number,
  aiCalls: number,
): string | null {
  // 판정별 문구
  switch (verdict) {
    case "full_success":
      // 사용자가 먼저 맞혔으면 AI 수사관의 조사 횟수 강조
      return steps < aiCalls
        ? `AI 수사관은 ${aiCalls}번 조사한 끝에 같은 결론을 냈어요.`
        : `AI 수사관도 ${withObjectParticle(culpritName)} 지목했어요.`;
    case "partial_success":
      return `AI 수사관도 ${withObjectParticle(culpritName)} 지목했지만, 결정적인 단서를 다 찾지는 못했어요.`;
    case "appropriate_withhold":
      // 증거가 부족해 미룬 경우
      return "AI 수사관은 증거가 부족하다며 판단을 미뤘는데, 당신은 범인을 찾아냈어요. 정말 대단해요!";
    case "inappropriate_withhold":
      // 단서를 다 찾고도 미룬 경우
      return "AI 수사관은 단서를 다 찾고도 판단을 미뤘는데, 당신은 범인을 맞혔어요. 정말 대단해요!";
    case "failure":
      return "AI 수사관은 다른 사람을 지목했어요. AI 수사관보다 한 수 위예요!";
    default:
      // 오류는 덧붙이지 않음
      return null;
  }
}

// 결과 메시지 카드
// 맞힘(AI 수사관보다 먼저인지·AI 수사관 비교)·틀림·모르겠어요에 맞는 축하·안내 문구를 카드로 보여 주는 컴포넌트
export function ResultMessage({
  pick,
  pickedAtStep,
  aiToolCallCount,
  culpritId,
  culpritName,
  aiVerdict,
}: ResultMessageProps) {
  // 선택 결과 구분
  const correct = pick !== UNKNOWN_PICK && pick === culpritId;
  const unknown = pick === UNKNOWN_PICK;
  // 제목과 아래 줄
  let title: string;
  let detail: string | null;
  if (correct) {
    title = correctTitle(pickedAtStep, aiToolCallCount);
    detail = aiComparison(
      aiVerdict,
      culpritName,
      pickedAtStep,
      aiToolCallCount,
    );
  } else if (unknown) {
    title = `정답은 ${withWasEnding(culpritName)}.`;
    detail =
      "단서를 다시 보며 AI 수사관이 범인을 찾아가는 과정을 확인해 보세요.";
  } else {
    title = `아쉬워요. 범인은 ${withWasEnding(culpritName)}.`;
    detail = "단서를 다시 보면 어디서 갈렸는지 확인할 수 있어요.";
  }
  // 맞히면 강조 카드, 아니면 기본 카드
  const cardClass = correct
    ? "border-amber-400 bg-amber-100 text-slate-900"
    : "border-slate-700 bg-slate-900 text-slate-100";
  return (
    <div className={`rounded-lg border p-4 ${cardClass}`}>
      {/* 제목 */}
      <p className="text-lg font-bold">{title}</p>
      {/* 아래 줄 */}
      {detail && <p className="mt-1 text-sm">{detail}</p>}
    </div>
  );
}
