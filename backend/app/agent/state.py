from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from app.schemas.plan import InvestigationPlan
from app.schemas.report import FinalReport

# 보고서 오류 종류
ReportErrorKind = Literal[
    "parse", "invalid_suspect", "uncollected_evidence", "missing_evidence"
]


# 보고서 오류
# 최종 보고서 작성 시도 하나에서 발견된 오류의 시도 번호·종류·내용을 담는 클래스
class ReportError(TypedDict):
    # 보고서 작성 시도 번호 (1부터)
    attempt: int
    # 오류 종류
    kind: ReportErrorKind
    # 오류 내용
    detail: str


# 확보 증거
# 수사 중 확보한 증거의 ID·출처·요약·확보 순번을 담는 클래스
class CollectedEvidence(TypedDict):
    # 증거 ID
    id: str
    # 증거를 내놓은 조사 도구
    source_tool: str
    # 증거 요약 문장
    summary: str
    # 확보한 도구 호출 순번
    step: int


# 조사 기록 항목
# 도구 호출 한 번의 순번·도구·인자·이유·결과를 담는 클래스
class HistoryEntry(TypedDict):
    # 도구 호출 순번 (1부터)
    step: int
    # 호출한 도구 이름
    tool: str
    # 도구 인자 (reason 제외)
    args: dict[str, Any]
    # 도구를 고른 이유 (없으면 None)
    reason: str | None
    # 호출 시점의 현재 가설 (값을 얻지 못하면 None)
    hypothesis: str | None
    # 증거 발견 여부 (교차 검증·오류는 None)
    found: bool | None
    # 이번 호출로 반환된 증거 ID
    evidence_ids: list[str]
    # 오류 메시지 (성공이면 None)
    error: str | None


# 수사 상태
# LangGraph 수사 그래프가 단계마다 주고받는 상태를 정의하는 클래스
class InvestigationState(TypedDict):
    # 사건 ID
    case_id: str
    # 실행 방식
    mode: Literal["adaptive", "fixed"]
    # LLM 대화·도구 메시지 (add_messages로 누적)
    messages: Annotated[list[AnyMessage], add_messages]
    # 확보한 증거 (증거 ID → 정보)
    collected_evidence: dict[str, CollectedEvidence]
    # 조사 기록
    investigation_history: list[HistoryEntry]
    # 실제 도구 호출 횟수
    tool_call_count: int
    # 진행 상태
    status: Literal["pending", "running", "completed", "inconclusive", "failed"]
    # 수사 종료 사유
    stop_reason: (
        Literal["finished", "budget_exhausted", "llm_error", "plan_error"] | None
    )
    # 고정 계획형 조사 계획 (적응형은 None)
    plan: InvestigationPlan | None
    # 검증 대기 보고서
    pending_report: FinalReport | None
    # 최종 보고서 (검증 통과 또는 강제 판단 보류 후 저장)
    final_report: FinalReport | None
    # 보고서 처리 결과
    report_status: Literal["accepted", "forced_withhold"] | None
    # 증거·용의자 인용 오류로 거절된 횟수
    validation_rejections: int
    # 보고서 오류 기록
    report_errors: list[ReportError]
    # 오류 설명
    error: str | None
