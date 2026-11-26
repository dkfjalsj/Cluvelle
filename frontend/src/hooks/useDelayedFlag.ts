import { useEffect, useState } from "react";

// 지연 표시 훅
// active가 true인 상태로 delayMs가 지나면 true가 되는 값을 반환하는 커스텀 훅 (active가 false면 즉시 false)
export function useDelayedFlag(active: boolean, delayMs: number): boolean {
  // 지연 시간이 지났는지 여부
  const [elapsed, setElapsed] = useState(false);

  // active가 켜지면 타이머 시작, 꺼지거나 바뀌면 정리
  useEffect(() => {
    // 비활성이면 타이머 없음
    if (!active) {
      return;
    }
    // 지연 후 true로 변경
    const timer = window.setTimeout(() => setElapsed(true), delayMs);
    // 정리: 타이머 해제 후 다시 false
    return () => {
      window.clearTimeout(timer);
      setElapsed(false);
    };
  }, [active, delayMs]);

  // 활성 상태일 때만 지연 결과 반환
  return active && elapsed;
}
