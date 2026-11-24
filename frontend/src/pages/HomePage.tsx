import { HealthStatus } from "../components/HealthStatus";
import { useHealth } from "../hooks/useHealth";

// 홈 페이지
// 앱 이름과 백엔드 연결 상태를 보여주는 컴포넌트
export function HomePage() {
  // 백엔드 헬스 체크 상태 조회
  const healthState = useHealth();

  return (
    // 어두운 배경의 전체 화면 영역 (가로 넘침 방지)
    <main className="min-h-screen overflow-x-hidden bg-slate-950 px-4 py-10 text-slate-100">
      {/* 앱 이름 */}
      <h1 className="text-2xl font-bold">Cluvelle</h1>
      {/* 백엔드 연결 상태 */}
      <div className="mt-4">
        <HealthStatus state={healthState} />
      </div>
    </main>
  );
}
