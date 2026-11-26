// 범인 선택 값 (용의자 ID 또는 "모르겠어요")
export type SuspectPick = string;

// "모르겠어요" 선택 값
export const UNKNOWN_PICK = "unknown";

// 수사 화면 진행 상태
// 안내문을 닫았는지·공개한 단계 수·고른 용의자·고른 시점 단계를 담는 타입 (브라우저에 저장)
export interface InvestigationProgress {
  // 안내문을 닫았는지
  guideClosed: boolean;
  // 공개한 단계 수
  revealedSteps: number;
  // 고른 용의자 ID 또는 "unknown" (아직 안 골랐으면 null)
  pickedSuspect: SuspectPick | null;
  // 고른 시점의 공개 단계 수 (아직 안 골랐으면 null)
  pickedAtStep: number | null;
}
