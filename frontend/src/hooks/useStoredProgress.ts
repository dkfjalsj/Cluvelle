import { useCallback, useEffect, useState } from "react";

import type { InvestigationProgress } from "../types/progress";

// 처음 진행 상태
const INITIAL_PROGRESS: InvestigationProgress = {
  guideClosed: false,
  revealedSteps: 0,
  pickedSuspect: null,
  pickedAtStep: null,
};

// 저장 키 만들기
// 수사 ID별 브라우저 저장 키를 만드는 함수
function storageKey(investigationId: string): string {
  // cluvelle:investigation:{id}
  return `cluvelle:investigation:${investigationId}`;
}

// 저장된 진행 상태 읽기
// 브라우저 저장소에서 진행 상태를 읽어 형식이 맞으면 반환하고, 없거나 실패하면 처음 상태를 반환하는 함수
function readProgress(investigationId: string): InvestigationProgress {
  try {
    // 저장 값 읽기
    const raw = window.localStorage.getItem(storageKey(investigationId));
    if (!raw) return INITIAL_PROGRESS;
    const value = JSON.parse(raw) as Partial<InvestigationProgress>;
    // 필드별 형식 확인 후 복원 (틀린 값은 처음 값)
    return {
      guideClosed: value.guideClosed === true,
      revealedSteps:
        typeof value.revealedSteps === "number" && value.revealedSteps >= 0
          ? Math.floor(value.revealedSteps)
          : 0,
      pickedSuspect:
        typeof value.pickedSuspect === "string" ? value.pickedSuspect : null,
      pickedAtStep:
        typeof value.pickedAtStep === "number" ? value.pickedAtStep : null,
    };
  } catch {
    // 읽기 실패면 저장 없이 동작
    return INITIAL_PROGRESS;
  }
}

// 진행 상태 저장 훅
// 수사 ID별 진행 상태를 브라우저 저장소에서 복원하고 바뀔 때마다 저장하는 커스텀 훅
export function useStoredProgress(
  investigationId: string,
): [InvestigationProgress, (change: Partial<InvestigationProgress>) => void] {
  // 처음 렌더 때 저장 값으로 복원
  const [progress, setProgress] = useState<InvestigationProgress>(() =>
    readProgress(investigationId),
  );

  // 바뀔 때마다 저장 (실패하면 저장 없이 동작)
  useEffect(() => {
    try {
      window.localStorage.setItem(
        storageKey(investigationId),
        JSON.stringify(progress),
      );
    } catch {
      // 저장 실패는 무시
    }
  }, [investigationId, progress]);

  // 일부 값 바꾸기
  // 주어진 필드만 바꾼 새 진행 상태로 갱신하는 함수
  const update = useCallback((change: Partial<InvestigationProgress>) => {
    // 이전 상태에 변경 합치기
    setProgress((prev) => ({ ...prev, ...change }));
  }, []);

  // 상태와 변경 함수 반환
  return [progress, update];
}
