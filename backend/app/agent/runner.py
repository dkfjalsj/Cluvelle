"""수사 실행 함수.

mode="fixed"(고정 계획형)는 비교 실험 전용이며 공개 API로 노출하지 않는다. 서비스에서는 적응형만 쓴다.
"""

from typing import Literal, cast

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage

from app.agent.fixed_graph import build_fixed_graph
from app.agent.graph import build_investigation_graph
from app.agent.prompts import SYSTEM_PROMPT, build_case_brief
from app.agent.state import InvestigationState
from app.services.case_repository import CaseRepository

# 실행 방식
InvestigationMode = Literal["adaptive", "fixed"]


# 수사 실행
# 사건을 로드해 방식에 맞는 그래프를 끝까지 실행하고 최종 상태를 반환하는 함수
def run_investigation(
    case_id: str,
    llm: BaseChatModel,
    mode: InvestigationMode = "adaptive",
    repository: CaseRepository | None = None,
) -> InvestigationState:
    # 저장소가 없으면 기본 경로 저장소 사용
    repository = repository or CaseRepository()
    # 사건 로드와 공개 정보 변환
    case = repository.load_case(case_id)
    public_case = repository.get_public_case(case_id)

    # 방식별 그래프와 첫 메시지
    initial_messages: list[AnyMessage]
    if mode == "fixed":
        # 고정 계획형은 planner가 시스템 프롬프트·브리핑을 직접 구성하므로 비워 둠
        graph = build_fixed_graph(llm, case)
        initial_messages = []
    else:
        # 적응형은 시스템 프롬프트 + 사건 브리핑으로 시작
        graph = build_investigation_graph(llm, case)
        initial_messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=build_case_brief(public_case) + "\n수사를 시작하라."),
        ]

    # 초기 상태
    initial_state: InvestigationState = {
        "case_id": case.case_id,
        "mode": mode,
        "messages": initial_messages,
        "collected_evidence": {},
        "investigation_history": [],
        "tool_call_count": 0,
        "status": "running",
        "stop_reason": None,
        "plan": None,
        "pending_report": None,
        "final_report": None,
        "report_status": None,
        "validation_rejections": 0,
        "report_errors": [],
        "error": None,
    }
    # 반복 한도: 예산 × 2(수사관·도구 실행) + 마지막 수사관 1 + 보고서·검증 2회씩 4 + 여유 5
    # (고정 계획형은 계획 1 + 실행 1 + 보고서·검증 4로 이보다 훨씬 적음)
    recursion_limit = case.tool_budget * 2 + 10
    # 그래프 실행 후 최종 상태 반환
    result = graph.invoke(initial_state, config={"recursion_limit": recursion_limit})
    return cast(InvestigationState, result)
