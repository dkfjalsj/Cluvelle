from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agent.execution import TOOL_FUNCTIONS, describe_error, handle_tool_call
from app.agent.report_nodes import (
    REPORT_NODE,
    REPORT_VALIDATOR_NODE,
    make_report_node,
    make_report_validator,
    route_after_report,
    route_after_validator,
)
from app.agent.state import InvestigationState
from app.agent.tool_specs import get_llm_tools
from app.schemas.case import CaseFile

# 테스트에서 도구 함수를 바꿔 끼울 수 있도록 같은 표를 이 모듈 이름으로도 노출
__all__ = ["TOOL_FUNCTIONS", "build_investigation_graph"]

# 노드 이름
INVESTIGATOR_NODE = "investigator"
TOOL_EXECUTOR_NODE = "tool_executor"


# 적응형 수사 그래프 생성
# LLM과 사건을 받아 조사 반복·최종 보고서 작성·서버 검증까지 하는 LangGraph 그래프를 컴파일해 반환하는 함수
def build_investigation_graph(llm: BaseChatModel, case: CaseFile) -> CompiledStateGraph:
    # 도구 명세를 묶은 LLM
    llm_with_tools = llm.bind_tools(get_llm_tools())

    # 수사관 노드
    # 현재 메시지를 LLM에 보내 다음 행동(도구 호출 또는 수사 종료)을 받아 상태에 반영하는 함수
    def investigator(state: InvestigationState) -> dict[str, Any]:
        # LLM 호출 (실패하면 실패 상태로 종료)
        try:
            response = llm_with_tools.invoke(state["messages"])
        except Exception as error:  # noqa: BLE001
            # LLM 오류는 종류와 무관하게 실패 처리
            return {
                "status": "failed",
                "stop_reason": "llm_error",
                "error": describe_error(error),
            }
        # AIMessage가 아니면 AIMessage로 감싸기
        if not isinstance(response, AIMessage):
            response = AIMessage(content=response.content)
        # 도구 호출이 있으면 메시지만 추가
        if response.tool_calls:
            return {"messages": [response]}
        # 도구 호출이 없으면 수사 종료 (보고서 작성으로 이동)
        return {"messages": [response], "stop_reason": "finished"}

    # 도구 실행 노드
    # 마지막 AIMessage의 도구 호출을 순서대로 공통 규칙으로 처리해 상태에 반영하는 함수
    def tool_executor(state: InvestigationState) -> dict[str, Any]:
        # 마지막 AIMessage의 도구 호출 목록
        last_message = state["messages"][-1]
        tool_calls = (
            last_message.tool_calls if isinstance(last_message, AIMessage) else []
        )
        # 현재 상태 복사본
        count = state["tool_call_count"]
        collected = dict(state["collected_evidence"])
        history = list(state["investigation_history"])
        tool_messages: list[ToolMessage] = []

        # 도구 호출을 순서대로 공통 처리
        for tool_call in tool_calls:
            message, count = handle_tool_call(
                case, tool_call, count, collected, history
            )
            tool_messages.append(message)

        # 상태 변경분
        update: dict[str, Any] = {
            "messages": tool_messages,
            "tool_call_count": count,
            "collected_evidence": collected,
            "investigation_history": history,
        }
        # 예산을 모두 썼으면 수사 종료 (보고서 작성으로 이동)
        if count >= case.tool_budget:
            update["stop_reason"] = "budget_exhausted"
        # 변경분 반환
        return update

    # 수사관 다음 경로
    # 실패면 종료, 수사 종료면 보고서, 도구 호출이 있으면 도구 실행으로 보내는 함수
    def route_after_investigator(state: InvestigationState) -> str:
        # LLM 오류로 실패면 종료
        if state["status"] == "failed":
            return END
        # 수사 종료면 보고서 작성
        if state["stop_reason"] == "finished":
            return REPORT_NODE
        # 그 외(도구 호출 있음)는 도구 실행
        return TOOL_EXECUTOR_NODE

    # 도구 실행 다음 경로
    # 예산을 다 썼으면 보고서로, 아니면 수사관으로 보내는 함수
    def route_after_tools(state: InvestigationState) -> str:
        # 예산 소진이면 보고서 작성
        if state["tool_call_count"] >= case.tool_budget:
            return REPORT_NODE
        # 아니면 다음 조사 결정
        return INVESTIGATOR_NODE

    # 그래프 구성
    graph = StateGraph(InvestigationState)
    graph.add_node(INVESTIGATOR_NODE, investigator)
    graph.add_node(TOOL_EXECUTOR_NODE, tool_executor)
    graph.add_node(REPORT_NODE, make_report_node(llm, case))
    graph.add_node(REPORT_VALIDATOR_NODE, make_report_validator(case))
    # 시작 → 수사관
    graph.add_edge(START, INVESTIGATOR_NODE)
    # 수사관 → 도구 실행 / 보고서 / 종료
    graph.add_conditional_edges(
        INVESTIGATOR_NODE,
        route_after_investigator,
        [TOOL_EXECUTOR_NODE, REPORT_NODE, END],
    )
    # 도구 실행 → 수사관 / 보고서
    graph.add_conditional_edges(
        TOOL_EXECUTOR_NODE, route_after_tools, [INVESTIGATOR_NODE, REPORT_NODE]
    )
    # 보고서 → 검증 / 종료
    graph.add_conditional_edges(
        REPORT_NODE, route_after_report, [REPORT_VALIDATOR_NODE, END]
    )
    # 검증 → 종료 / 보고서 재작성
    graph.add_conditional_edges(
        REPORT_VALIDATOR_NODE, route_after_validator, [REPORT_NODE, END]
    )
    # 컴파일해 반환
    return graph.compile()
