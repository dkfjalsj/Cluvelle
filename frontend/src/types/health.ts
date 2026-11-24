// 헬스 체크 응답
// 백엔드 /api/health 응답 본문의 형태를 정의하는 타입
export interface HealthResponse {
  // 서버 상태 (정상일 때 "ok")
  status: "ok";
}
