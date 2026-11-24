import { useEffect, useState } from "react";

import { fetchHealth } from "../services/api";

// 헬스 체크 상태 값
export type HealthState = "loading" | "ok" | "error";

// 헬스 체크 훅
// 마운트 시 한 번 백엔드 상태를 확인해 loading/ok/error 상태를 반환하는 커스텀 훅
export function useHealth(): HealthState {
  // 현재 헬스 체크 상태 (처음에는 확인 중)
  const [state, setState] = useState<HealthState>("loading");

  // 마운트 시 1회 헬스 체크 실행
  useEffect(() => {
    // 언마운트 후 상태 변경을 막기 위한 플래그
    let isActive = true;
    // 헬스 체크 요청 후 결과에 따라 상태 갱신
    fetchHealth()
      .then(() => {
        // 정상 응답이면 ok로 변경
        if (isActive) setState("ok");
      })
      .catch(() => {
        // 실패하면 error로 변경
        if (isActive) setState("error");
      });
    // 정리 함수: 언마운트 시 플래그 해제
    return () => {
      isActive = false;
    };
  }, []);

  // 현재 상태 반환
  return state;
}
