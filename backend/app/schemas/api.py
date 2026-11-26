from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.case import Difficulty
from app.schemas.report import FinalReport
from app.schemas.tool import EvidenceView

# 수사 이벤트 종류
EventType = Literal[
    "tool_selected", "hypothesis_updated", "evidence_found", "finished", "error"
]
# 수사 진행 상태
RunStatus = Literal["pending", "running", "completed", "inconclusive", "failed"]
# 채점 판정
GradingVerdict = Literal[
    "full_success",
    "partial_success",
    "appropriate_withhold",
    "inappropriate_withhold",
    "failure",
    "error",
]


# 사건 목록 항목
# 사건 목록 API가 돌려주는 사건 하나의 요약 정보를 담는 클래스
class CaseListItem(BaseModel):
    # 사건 ID
    case_id: str
    # 사건 제목
    title: str
    # 난이도
    difficulty: Difficulty
    # 한 줄 소개
    summary: str
    # 조사 예산
    tool_budget: int


# 수사 시작 요청
# 수사 시작 API의 요청 본문(사건 ID만 허용)을 담는 클래스
class StartInvestigationRequest(BaseModel):
    # 정의되지 않은 필드는 거부
    model_config = ConfigDict(extra="forbid")

    # 수사할 사건 ID
    case_id: str


# 수사 시작 응답
# 수사 시작 API가 돌려주는 수사 ID·사건 ID·상태를 담는 클래스
class StartInvestigationResponse(BaseModel):
    # 수사 ID
    investigation_id: str
    # 사건 ID
    case_id: str
    # 진행 상태
    status: RunStatus


# 수사 이벤트
# SSE로 보내는 수사 진행 이벤트 하나(번호·종류·데이터)를 담는 클래스
class InvestigationEvent(BaseModel):
    # 0부터 1씩 늘어나는 이벤트 번호
    id: int
    # 이벤트 종류
    event: EventType
    # 이벤트 데이터
    data: dict[str, Any]


# 도구 선택 이벤트 데이터
# 수사관이 도구 호출을 낸 직후의 순번·도구·인자·이유를 담는 클래스
class ToolSelectedData(BaseModel):
    # 예정 순번
    step: int
    # 도구 이름
    tool: str
    # 도구 인자 (reason·hypothesis 제외)
    args: dict[str, Any]
    # 도구를 고른 이유
    reason: str | None


# 가설 변경 이벤트 데이터
# 도구 호출 시점의 새 가설을 담는 클래스
class HypothesisUpdatedData(BaseModel):
    # 순번
    step: int
    # 새 가설
    hypothesis: str


# 증거 확보 이벤트 데이터
# 도구 실행 결과(발견 여부·증거·오류·남은 예산)를 담는 클래스
class EvidenceFoundData(BaseModel):
    # 순번
    step: int
    # 도구 이름
    tool: str
    # 증거 발견 여부 (교차 검증·오류는 None)
    found: bool | None
    # 이번 호출로 반환된 증거 (사실 관계 제외)
    evidence: list[EvidenceView]
    # 오류 내용 (성공이면 None)
    error: str | None
    # 남은 조사 예산
    remaining_budget: int


# 종료 이벤트 데이터
# 그래프가 끝났을 때의 상태·종료 사유·보고서 처리 결과를 담는 클래스
class FinishedData(BaseModel):
    # 진행 상태
    status: RunStatus
    # 수사 종료 사유
    stop_reason: str | None
    # 보고서 처리 결과
    report_status: str | None


# 오류 이벤트 데이터
# 그래프 실행 중 예외가 났을 때의 사용자용 문장을 담는 클래스
class ErrorData(BaseModel):
    # 사용자용 짧은 문장
    message: str


# 조사 기록 응답 항목
# 결과 API에 담는 조사 기록 한 건을 담는 클래스
class HistoryItem(BaseModel):
    # 순번
    step: int
    # 도구 이름
    tool: str
    # 도구 인자 (reason·hypothesis 제외)
    args: dict[str, Any]
    # 도구를 고른 이유
    reason: str | None
    # 호출 시점의 가설
    hypothesis: str | None
    # 증거 발견 여부
    found: bool | None
    # 반환된 증거 ID
    evidence_ids: list[str]
    # 오류 내용
    error: str | None


# 확보 증거 응답 항목
# 결과 API에 담는 확보 증거 한 건(사실 관계 제외)을 담는 클래스
class CollectedEvidenceItem(BaseModel):
    # 증거 ID
    id: str
    # 증거를 내놓은 도구
    source_tool: str
    # 증거 요약 문장
    summary: str
    # 확보한 순번
    step: int


# 채점 결과
# 수사 최종 상태를 정답과 비교한 판정과 근거 수치를 담는 클래스
class GradingResult(BaseModel):
    # 판정
    verdict: GradingVerdict
    # 정답 범인 ID
    culprit_id: str
    # 정답 범인 이름
    culprit_name: str
    # 보고서가 지목한 용의자 ID (보류·보고서 없음이면 None)
    accused_suspect_id: str | None
    # 결정적 증거 ID
    decisive_evidence_ids: list[str]
    # 확보한 결정적 증거 ID
    collected_decisive_ids: list[str]
    # 보고서에서 인용한 결정적 증거 ID
    cited_decisive_ids: list[str]
    # 도구 호출 횟수
    tool_call_count: int
    # 보고서 검증 거절 횟수
    validation_rejections: int
    # 설계상 해결 경로 길이
    solution_path_length: int
    # 채점 메모
    grading_notes: str


# 수사 결과 응답
# 결과 API가 돌려주는 진행 상태·기록·확보 증거·보고서·채점을 담는 클래스
class InvestigationResultResponse(BaseModel):
    # 수사 ID
    investigation_id: str
    # 사건 ID
    case_id: str
    # 진행 상태
    status: RunStatus
    # 조사 예산
    tool_budget: int
    # 도구 호출 횟수
    tool_call_count: int
    # 조사 기록
    history: list[HistoryItem]
    # 확보 증거
    collected_evidence: list[CollectedEvidenceItem]
    # 최종 보고서 (종료 전 None)
    final_report: FinalReport | None
    # 보고서 처리 결과 (종료 전 None)
    report_status: str | None
    # 보고서 검증 거절 횟수 (종료 전 None)
    validation_rejections: int | None
    # 사용자용 오류 문장
    error: str | None
    # 채점 결과 (종료 상태일 때만)
    grading: GradingResult | None
