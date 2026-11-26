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

// 판정 표시 이름
export const VERDICT_LABELS: Record<GradingVerdict, string> = {
  full_success: "완전 성공",
  partial_success: "부분 성공",
  appropriate_withhold: "적절한 보류",
  inappropriate_withhold: "부적절한 보류",
  failure: "실패",
  error: "오류",
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
