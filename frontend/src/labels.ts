import type { Difficulty, GradingVerdict, RunStatus } from "./types/api";

// 도구 표시 이름
export const TOOL_LABELS: Record<string, string> = {
  inspect_scene: "현장 조사",
  interview_suspect: "심문",
  check_cctv: "CCTV 확인",
  verify_alibi: "알리바이 확인",
  cross_check_evidence: "교차 검증",
};

// 난이도 표시 이름
export const DIFFICULTY_LABELS: Record<Difficulty, string> = {
  intro: "입문",
  normal: "보통",
  challenge: "도전",
};

// 판정 표시 문구 (AI 판정 카드의 제목과 설명)
export const VERDICT_LABELS: Record<
  GradingVerdict,
  { title: string; description: string }
> = {
  full_success: {
    title: "AI가 범인을 맞혔어요",
    description: "결정적인 단서를 모두 찾고, 보고서에 근거로 썼어요.",
  },
  partial_success: {
    title: "AI가 범인을 맞혔지만 근거가 일부 부족해요",
    description:
      "결정적인 단서 중 일부를 찾지 못했거나 보고서에 근거로 쓰지 않았어요.",
  },
  appropriate_withhold: {
    title: "AI가 신중하게 판단을 미뤘어요",
    description:
      "결정적인 단서를 다 찾지 못해서 범인을 단정하지 않았어요. 근거 없이 지목하지 않은 합리적인 선택이에요.",
  },
  inappropriate_withhold: {
    title: "AI가 단서를 다 찾고도 판단을 미뤘어요",
    description:
      "결정적인 단서를 모두 찾았기 때문에 범인을 지목할 수 있었어요.",
  },
  failure: {
    title: "AI가 범인을 잘못 지목했어요",
    description: "단서를 잘못 해석해 다른 사람을 지목했어요.",
  },
  error: {
    title: "AI 수사 중 오류가 발생했어요",
    description: "수사를 끝까지 마치지 못했어요.",
  },
};

// 진행 상태 표시 이름
export const STATUS_LABELS: Record<RunStatus, string> = {
  pending: "진행 중",
  running: "진행 중",
  completed: "완료",
  inconclusive: "판단 보류",
  failed: "실패",
};

// 도구 표시 이름 조회
// 도구 이름의 한국어 표시 이름을 반환하고 모르는 도구면 원래 이름을 반환하는 함수
export function toolLabel(tool: string): string {
  // 표에 있으면 한국어, 없으면 원래 이름
  return TOOL_LABELS[tool] ?? tool;
}
