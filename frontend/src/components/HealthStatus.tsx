import type { HealthState } from "../hooks/useHealth";

// 헬스 상태 표시 속성
interface HealthStatusProps {
  // 표시할 헬스 체크 상태
  state: HealthState;
}

// 상태별 표시 문구
const statusLabels: Record<HealthState, string> = {
  loading: "확인 중",
  ok: "서버 정상",
  error: "서버 연결 실패",
};

// 상태별 글자 색상 클래스
const statusColors: Record<HealthState, string> = {
  loading: "text-slate-400",
  ok: "text-emerald-400",
  error: "text-red-400",
};

// 헬스 상태 표시
// 백엔드 연결 상태를 받아 정상/오류/확인 중 문구를 보여주는 컴포넌트
export function HealthStatus({ state }: HealthStatusProps) {
  // 상태에 맞는 문구와 색상으로 표시
  return (
    <p className={`text-sm ${statusColors[state]}`} role="status">
      {statusLabels[state]}
    </p>
  );
}
