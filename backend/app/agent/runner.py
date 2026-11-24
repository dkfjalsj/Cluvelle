from typing import cast

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.graph import build_investigation_graph
from app.agent.prompts import SYSTEM_PROMPT, build_case_brief
from app.agent.state import InvestigationState
from app.services.case_repository import CaseRepository


# 수사 실행
# 사건을 로드해 공개 정보로 첫 메시지를 만들고 수사 그래프를 끝까지 실행해 최종 상태를 반환하는 함수
def run_investigation(
    case_id: str,
    llm: BaseChatModel,
    repository: CaseRepository | None = None,
) -> InvestigationState:
    # 저장소가 없으면 기본 경로 저장소 사용
    repository = repository or CaseRepository()
    # 사건 로드와 공개 정보 변환
    case = repository.load_case(case_id)
    public_case = repository.get_public_case(case_id)
    # 초기 상태 (시스템 프롬프트 + 사건 브리핑)
    initial_state: InvestigationState = {
        "case_id": case.case_id,
        "mode": "adaptive",
        "messages": [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=build_case_brief(public_case) + "\n수사를 시작하라."),
        ],
        "collected_evidence": {},
        "investigation_history": [],
        "tool_call_count": 0,
        "status": "running",
        "stop_reason": None,
        "final_text": None,
        "error": None,
    }
    # 그래프 생성
    graph = build_investigation_graph(llm, case)
    # 반복 한도: 예산 × 2(수사관·도구 실행) + 여유 5
    recursion_limit = case.tool_budget * 2 + 5
    # 그래프 실행 후 최종 상태 반환
    result = graph.invoke(initial_state, config={"recursion_limit": recursion_limit})
    return cast(InvestigationState, result)
