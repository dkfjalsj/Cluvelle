// 난이도 값
export type Difficulty = "intro" | "normal" | "challenge";

// 수사 진행 상태
export type RunStatus =
  "pending" | "running" | "completed" | "inconclusive" | "failed";

// 채점 판정
export type GradingVerdict =
  | "full_success"
  | "partial_success"
  | "appropriate_withhold"
  | "inappropriate_withhold"
  | "failure"
  | "error";

// 사건 목록 항목
// 사건 목록 API가 돌려주는 사건 하나의 요약 정보 타입
export interface CaseListItem {
  // 사건 ID
  case_id: string;
  // 사건 제목
  title: string;
  // 난이도
  difficulty: Difficulty;
  // 한 줄 소개
  summary: string;
  // 조사 예산
  tool_budget: number;
}

// 용의자
// 공개 사건 정보의 용의자 타입
export interface Suspect {
  // 용의자 ID
  id: string;
  // 이름
  name: string;
  // 역할
  role: string;
  // 소개
  description: string;
}

// 장소
// 공개 사건 정보의 장소 타입
export interface Location {
  // 장소 ID
  id: string;
  // 장소 이름
  name: string;
  // 장소 설명 (없을 수 있음)
  description?: string | null;
}

// 카메라
// 공개 사건 정보의 카메라 타입
export interface Camera {
  // 카메라 ID
  id: string;
  // 카메라 이름
  name: string;
  // 카메라 설명 (없을 수 있음)
  description?: string | null;
  // 설치 장소 ID
  location_id: string;
  // 조회 가능한 시간대
  time_windows: string[];
}

// 질문 주제
// 공개 사건 정보의 질문 주제 타입
export interface Topic {
  // 주제 ID
  id: string;
  // 주제 이름
  name: string;
}

// 공개 사건 정보
// 사건 상세 API가 돌려주는 공개 정보 타입
export interface PublicCase {
  // 사건 ID
  case_id: string;
  // 사건 데이터 버전
  version: number;
  // 사건 제목
  title: string;
  // 난이도
  difficulty: Difficulty;
  // 한 줄 소개
  summary: string;
  // 사건 도입부
  introduction: string;
  // 사건 밖 장소 표기
  off_site_label: string;
  // 조사 예산
  tool_budget: number;
  // 용의자 목록
  suspects: Suspect[];
  // 장소 목록
  locations: Location[];
  // 카메라 목록
  cameras: Camera[];
  // 질문 주제 목록
  topics: Topic[];
}

// 수사 시작 응답
// 수사 시작 API가 돌려주는 수사 ID·사건 ID·상태 타입
export interface StartInvestigationResponse {
  // 수사 ID
  investigation_id: string;
  // 사건 ID
  case_id: string;
  // 진행 상태
  status: RunStatus;
}

// 증거 보기
// 이벤트·결과에 담기는 증거의 ID·출처·요약 타입
export interface EvidenceView {
  // 증거 ID
  id: string;
  // 증거를 내놓은 도구
  source_tool: string;
  // 증거 요약
  summary: string;
}

// 도구 선택 이벤트 데이터
// 수사관이 도구 호출을 낸 직후의 순번·도구·인자·이유 타입
export interface ToolSelectedData {
  // 순번
  step: number;
  // 도구 이름
  tool: string;
  // 도구 인자 (reason·hypothesis 제외)
  args: Record<string, unknown>;
  // 선택 이유
  reason: string | null;
}

// 가설 변경 이벤트 데이터
// 도구 호출 시점의 새 가설 타입
export interface HypothesisUpdatedData {
  // 순번
  step: number;
  // 새 가설
  hypothesis: string;
}

// 증거 확보 이벤트 데이터
// 도구 실행 결과(발견 여부·증거·오류·남은 예산) 타입
export interface EvidenceFoundData {
  // 순번
  step: number;
  // 도구 이름
  tool: string;
  // 증거 발견 여부 (교차 검증·오류는 null)
  found: boolean | null;
  // 반환된 증거
  evidence: EvidenceView[];
  // 오류 내용
  error: string | null;
  // 남은 조사 예산
  remaining_budget: number;
}

// 종료 이벤트 데이터
// 그래프가 끝났을 때의 상태·종료 사유·보고서 처리 결과 타입
export interface FinishedData {
  // 진행 상태
  status: RunStatus;
  // 수사 종료 사유
  stop_reason: string | null;
  // 보고서 처리 결과
  report_status: string | null;
}

// 오류 이벤트 데이터
// 그래프 실행 중 예외가 났을 때의 사용자용 문장 타입
export interface ErrorEventData {
  // 사용자용 문장
  message: string;
}

// 수사 이벤트
// SSE로 받는 수사 이벤트(번호·종류·데이터) 타입
export type InvestigationEvent =
  | { id: number; event: "tool_selected"; data: ToolSelectedData }
  | { id: number; event: "hypothesis_updated"; data: HypothesisUpdatedData }
  | { id: number; event: "evidence_found"; data: EvidenceFoundData }
  | { id: number; event: "finished"; data: FinishedData }
  | { id: number; event: "error"; data: ErrorEventData };

// 이벤트 종류
export type InvestigationEventType = InvestigationEvent["event"];

// 조사 기록 항목
// 결과 API의 조사 기록 한 건 타입
export interface HistoryItem {
  // 순번
  step: number;
  // 도구 이름
  tool: string;
  // 도구 인자
  args: Record<string, unknown>;
  // 선택 이유
  reason: string | null;
  // 호출 시점 가설
  hypothesis: string | null;
  // 증거 발견 여부
  found: boolean | null;
  // 반환된 증거 ID
  evidence_ids: string[];
  // 오류 내용
  error: string | null;
}

// 확보 증거 항목
// 결과 API의 확보 증거 한 건 타입
export interface CollectedEvidenceItem {
  // 증거 ID
  id: string;
  // 증거를 내놓은 도구
  source_tool: string;
  // 증거 요약
  summary: string;
  // 확보한 순번
  step: number;
}

// 최종 보고서
// 수사 결과(지목 또는 판단 보류)와 근거를 담은 보고서 타입
export interface FinalReport {
  // 결론 종류
  verdict: "accuse" | "withhold";
  // 지목한 용의자 ID
  suspect_id: string | null;
  // 인용한 증거 ID
  cited_evidence_ids: string[];
  // 발견한 불일치
  contradictions: string[];
  // 확인하지 못한 사항
  unverified: string[];
  // 추론 설명
  explanation: string;
}

// 채점 결과
// 정답과 비교한 판정과 근거 수치 타입
export interface GradingResult {
  // 판정
  verdict: GradingVerdict;
  // 정답 범인 ID
  culprit_id: string;
  // 정답 범인 이름
  culprit_name: string;
  // 보고서가 지목한 용의자 ID
  accused_suspect_id: string | null;
  // 결정적 증거 ID
  decisive_evidence_ids: string[];
  // 확보한 결정적 증거 ID
  collected_decisive_ids: string[];
  // 인용한 결정적 증거 ID
  cited_decisive_ids: string[];
  // 도구 호출 횟수
  tool_call_count: number;
  // 보고서 검증 거절 횟수
  validation_rejections: number;
  // 설계상 해결 경로 길이
  solution_path_length: number;
  // 채점 메모
  grading_notes: string;
}

// 수사 결과
// 결과 API가 돌려주는 진행 상태·기록·확보 증거·보고서·채점 타입
export interface InvestigationResult {
  // 수사 ID
  investigation_id: string;
  // 사건 ID
  case_id: string;
  // 진행 상태
  status: RunStatus;
  // 조사 예산
  tool_budget: number;
  // 도구 호출 횟수
  tool_call_count: number;
  // 조사 기록
  history: HistoryItem[];
  // 확보 증거
  collected_evidence: CollectedEvidenceItem[];
  // 최종 보고서 (종료 전 null)
  final_report: FinalReport | null;
  // 보고서 처리 결과 (종료 전 null)
  report_status: string | null;
  // 보고서 검증 거절 횟수 (종료 전 null)
  validation_rejections: number | null;
  // 사용자용 오류 문장
  error: string | null;
  // 채점 결과 (종료 상태일 때만)
  grading: GradingResult | null;
}
