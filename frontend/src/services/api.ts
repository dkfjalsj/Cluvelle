import type {
  CaseListItem,
  InvestigationResult,
  PublicCase,
  StartInvestigationResponse,
} from "../types/api";

// API 오류
// 서버 오류 응답의 HTTP 상태·오류 코드·안내 문장을 담는 오류 클래스
export class ApiError extends Error {
  // HTTP 상태 코드 (연결 실패는 0)
  readonly status: number;
  // 서버 오류 코드 (형식이 다르면 null)
  readonly code: string | null;

  // 오류 생성
  // 상태 코드·오류 코드·안내 문장으로 오류를 만드는 함수
  constructor(status: number, code: string | null, message: string) {
    // 부모 오류에 안내 문장 전달
    super(message);
    // 이름과 값 보관
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

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

// 오류 응답 해석
// 실패 응답 본문에서 {"detail": {"code", "message"}}를 읽어 ApiError로 만드는 함수
async function toApiError(response: Response): Promise<ApiError> {
  // 기본 문장 (형식이 다를 때)
  const fallback = new ApiError(
    response.status,
    null,
    `서버 오류(HTTP ${response.status})`,
  );
  // 본문을 JSON으로 읽기 (실패하면 기본 문장)
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    return fallback;
  }
  // detail 객체에 code·message 문자열이 있어야 함
  if (typeof body !== "object" || body === null || !("detail" in body)) {
    return fallback;
  }
  const detail = (body as { detail: unknown }).detail;
  if (
    typeof detail === "object" &&
    detail !== null &&
    "code" in detail &&
    "message" in detail &&
    typeof detail.code === "string" &&
    typeof detail.message === "string"
  ) {
    return new ApiError(response.status, detail.code, detail.message);
  }
  // 형식이 다르면 기본 문장
  return fallback;
}

// JSON 요청
// API 경로로 요청을 보내고 성공 응답 본문을 지정한 타입으로 반환하는 함수
async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  // 요청 전송 (네트워크 실패는 연결 실패 오류로)
  let response: Response;
  try {
    response = await fetch(`${getApiBaseUrl()}${path}`, init);
  } catch {
    throw new ApiError(0, null, "서버에 연결하지 못했어요.");
  }
  // 실패 응답이면 오류 객체로 던짐
  if (!response.ok) {
    throw await toApiError(response);
  }
  // 성공 본문 반환
  return (await response.json()) as T;
}

// 사건 목록 조회
// 사건 목록(ID·제목·난이도·소개·예산)을 가져오는 함수
export function fetchCases(): Promise<CaseListItem[]> {
  // GET /api/cases
  return requestJson<CaseListItem[]>("/api/cases");
}

// 사건 상세 조회
// 사건의 공개 정보를 가져오는 함수
export function fetchCase(caseId: string): Promise<PublicCase> {
  // GET /api/cases/{caseId}
  return requestJson<PublicCase>(`/api/cases/${encodeURIComponent(caseId)}`);
}

// 수사 시작
// 사건 ID로 적응형 수사를 시작하고 수사 ID를 받는 함수
export function startInvestigation(
  caseId: string,
): Promise<StartInvestigationResponse> {
  // POST /api/investigations
  return requestJson<StartInvestigationResponse>("/api/investigations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ case_id: caseId }),
  });
}

// 수사 결과 조회
// 수사의 진행 상태·기록·보고서·채점을 가져오는 함수
export function fetchInvestigationResult(
  investigationId: string,
): Promise<InvestigationResult> {
  // GET /api/investigations/{id}/result
  return requestJson<InvestigationResult>(
    `/api/investigations/${encodeURIComponent(investigationId)}/result`,
  );
}

// 이벤트 스트림 URL 만들기
// 수사 이벤트 SSE 주소를 만들고, 마지막 이벤트 번호가 있으면 last_event_id 쿼리를 붙이는 함수
export function buildEventStreamUrl(
  investigationId: string,
  lastEventId: number | null,
): string {
  // 기본 주소
  const url = `${getApiBaseUrl()}/api/investigations/${encodeURIComponent(investigationId)}/events`;
  // 이어 받기 번호가 있으면 쿼리 추가
  return lastEventId === null ? url : `${url}?last_event_id=${lastEventId}`;
}
