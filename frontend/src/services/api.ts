import type { HealthResponse } from "../types/health";

// API 기본 URL 조회
// 환경변수 VITE_API_BASE_URL을 읽고 값이 없으면 오류를 던지는 함수
function getApiBaseUrl(): string {
  // 빌드 시 주입된 환경변수 읽기
  const baseUrl = import.meta.env.VITE_API_BASE_URL;
  // 값이 비어 있으면 설정 누락 오류 발생
  if (!baseUrl) {
    throw new Error("VITE_API_BASE_URL 환경변수가 설정되지 않았습니다.");
  }
  // 끝의 슬래시를 제거해 경로 결합 시 중복 방지
  return baseUrl.replace(/\/+$/, "");
}

// 헬스 체크 호출
// 백엔드 GET /api/health를 호출해 서버 상태를 반환하는 함수
export async function fetchHealth(): Promise<HealthResponse> {
  // 헬스 체크 API 요청
  const response = await fetch(`${getApiBaseUrl()}/api/health`);
  // 200이 아니면 오류 발생
  if (response.status !== 200) {
    throw new Error(`헬스 체크 실패: HTTP ${response.status}`);
  }
  // 응답 본문을 헬스 체크 타입으로 변환해 반환
  return (await response.json()) as HealthResponse;
}
