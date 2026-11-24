import re
from collections.abc import Callable
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolCall, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, ValidationError

from app.agent.state import CollectedEvidence, HistoryEntry, InvestigationState
from app.agent.tool_specs import TOOL_INPUT_MODELS, get_llm_tools
from app.schemas.case import CaseFile
from app.schemas.tool import InvestigationResult
from app.tools import (
    ToolArgumentError,
    check_cctv,
    cross_check_evidence,
    inspect_scene,
    interview_suspect,
    verify_alibi,
)

# 도구 이름 → 실제 도구 함수 (첫 인자는 사건)
TOOL_FUNCTIONS: dict[str, Callable[..., BaseModel]] = {
    "inspect_scene": inspect_scene,
    "interview_suspect": interview_suspect,
    "check_cctv": check_cctv,
    "verify_alibi": verify_alibi,
    "cross_check_evidence": cross_check_evidence,
}

# 노드 이름
INVESTIGATOR_NODE = "investigator"
TOOL_EXECUTOR_NODE = "tool_executor"

# 예산 소진 안내 문구
BUDGET_EXHAUSTED_MESSAGE = (
    "조사 예산을 모두 사용했습니다. 더 이상 도구를 호출할 수 없습니다."
)
# 도구 인자 오류 문구 접두어
TOOL_ARGUMENT_ERROR_PREFIX = "도구 인자 오류: "

# 오류 메시지에서 가릴 API 키 패턴 (Google API 키 형식, URL의 key 파라미터)
SECRET_PATTERNS = (
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"AQ\.[0-9A-Za-z_\-]{20,}"),
    re.compile(r"(key=)[^&\s]+", re.IGNORECASE),
)


# 수사 그래프 생성
# LLM과 사건을 받아 조사 도구 선택·실행을 반복하는 LangGraph 그래프를 컴파일해 반환하는 함수
def build_investigation_graph(llm: BaseChatModel, case: CaseFile) -> CompiledStateGraph:
    # 도구 명세를 묶은 LLM
    llm_with_tools = llm.bind_tools(get_llm_tools())

    # 수사관 노드
    # 현재 메시지를 LLM에 보내 다음 행동(도구 호출 또는 결론)을 받아 상태에 반영하는 함수
    def investigator(state: InvestigationState) -> dict[str, Any]:
        # LLM 호출 (실패하면 실패 상태로 종료)
        try:
            response = llm_with_tools.invoke(state["messages"])
        except Exception as error:  # noqa: BLE001
            # LLM 오류는 종류와 무관하게 실패 처리
            return {
                "status": "failed",
                "stop_reason": "llm_error",
                "error": _describe_error(error),
            }
        # AIMessage가 아니면 AIMessage로 감싸기
        if not isinstance(response, AIMessage):
            response = AIMessage(content=response.content)
        # 도구 호출이 있으면 메시지만 추가
        if response.tool_calls:
            return {"messages": [response]}
        # 도구 호출이 없으면 결론으로 보고 완료 처리
        return {
            "messages": [response],
            "status": "completed",
            "stop_reason": "finished",
            "final_text": response.text,
        }

    # 도구 실행 노드
    # 마지막 AIMessage의 도구 호출을 순서대로 실행해 ToolMessage·증거·기록을 상태에 반영하는 함수
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

        # 도구 호출을 순서대로 처리
        for tool_call in tool_calls:
            # 예산을 다 썼으면 실행하지 않고 안내만 (차감 없음)
            if count >= case.tool_budget:
                tool_messages.append(_tool_message(BUDGET_EXHAUSTED_MESSAGE, tool_call))
                continue
            # 호출 횟수 차감
            count += 1
            # 도구 실행 후 메시지·기록 생성
            content, entry = _execute_tool_call(case, tool_call, count, collected)
            tool_messages.append(_tool_message(content, tool_call))
            history.append(entry)

        # 상태 변경분
        update: dict[str, Any] = {
            "messages": tool_messages,
            "tool_call_count": count,
            "collected_evidence": collected,
            "investigation_history": history,
        }
        # 예산을 모두 썼으면 판단 보류 상태로 종료 표시
        if count >= case.tool_budget:
            update["status"] = "inconclusive"
            update["stop_reason"] = "budget_exhausted"
        # 변경분 반환
        return update

    # 수사관 다음 경로
    # 실패면 종료, 도구 호출이 있으면 도구 실행, 없으면 종료로 보내는 함수
    def route_after_investigator(state: InvestigationState) -> str:
        # 실패 또는 완료 상태면 종료
        if state["status"] in ("failed", "completed"):
            return END
        # 도구 호출이 있으면 도구 실행 노드로
        return TOOL_EXECUTOR_NODE

    # 도구 실행 다음 경로
    # 예산을 다 썼으면 종료, 아니면 수사관으로 보내는 함수
    def route_after_tools(state: InvestigationState) -> str:
        # 예산 소진이면 종료
        if state["tool_call_count"] >= case.tool_budget:
            return END
        # 아니면 다음 조사 결정
        return INVESTIGATOR_NODE

    # 그래프 구성
    graph = StateGraph(InvestigationState)
    graph.add_node(INVESTIGATOR_NODE, investigator)
    graph.add_node(TOOL_EXECUTOR_NODE, tool_executor)
    # 시작 → 수사관
    graph.add_edge(START, INVESTIGATOR_NODE)
    # 수사관 → 도구 실행 또는 종료
    graph.add_conditional_edges(
        INVESTIGATOR_NODE, route_after_investigator, [TOOL_EXECUTOR_NODE, END]
    )
    # 도구 실행 → 수사관 또는 종료
    graph.add_conditional_edges(
        TOOL_EXECUTOR_NODE, route_after_tools, [INVESTIGATOR_NODE, END]
    )
    # 컴파일해 반환
    return graph.compile()


# 도구 호출 실행
# 도구 호출 하나의 인자를 검증해 실행하고 ToolMessage 내용과 조사 기록을 반환하는 함수
def _execute_tool_call(
    case: CaseFile,
    tool_call: ToolCall,
    step: int,
    collected: dict[str, CollectedEvidence],
) -> tuple[str, HistoryEntry]:
    # 도구 이름과 원본 인자
    name = tool_call["name"]
    raw_args = dict(tool_call.get("args") or {})
    # 기록용 인자(reason 제외)와 이유
    record_args = {key: value for key, value in raw_args.items() if key != "reason"}
    raw_reason = raw_args.get("reason")
    reason = raw_reason if isinstance(raw_reason, str) else None

    # 알 수 없는 도구 이름이면 인자 오류로 처리
    input_model = TOOL_INPUT_MODELS.get(name)
    tool_function = TOOL_FUNCTIONS.get(name)
    if input_model is None or tool_function is None:
        message = f"알 수 없는 도구입니다: {name}"
        return _error_result(name, record_args, reason, step, message)

    # 입력 모델로 인자 검증
    try:
        validated = input_model.model_validate(raw_args)
    except ValidationError as error:
        return _error_result(name, record_args, reason, step, _summarize(error))

    # 검증된 인자 (reason 제외)와 정리된 이유
    call_args = validated.model_dump(exclude={"reason"})
    reason = getattr(validated, "reason", reason)
    # 실제 도구 함수 호출
    try:
        result = tool_function(case, **call_args)
    except ToolArgumentError as error:
        return _error_result(name, call_args, reason, step, str(error))

    # 조회 도구 결과면 새 증거를 확보 목록에 추가
    found: bool | None = None
    evidence_ids: list[str] = []
    if isinstance(result, InvestigationResult):
        found = result.found
        evidence_ids = [item.id for item in result.evidence]
        for item in result.evidence:
            # 이미 확보한 증거는 처음 기록 유지
            if item.id not in collected:
                collected[item.id] = CollectedEvidence(
                    id=item.id,
                    source_tool=item.source_tool,
                    summary=item.summary,
                    step=step,
                )
    # 조사 기록 생성
    entry = HistoryEntry(
        step=step,
        tool=name,
        args=call_args,
        reason=reason,
        found=found,
        evidence_ids=evidence_ids,
        error=None,
    )
    # 결과 JSON과 기록 반환
    return result.model_dump_json(), entry


# 오류 결과 생성
# 인자 오류를 ToolMessage 내용과 조사 기록으로 만드는 함수
def _error_result(
    name: str,
    args: dict[str, Any],
    reason: str | None,
    step: int,
    message: str,
) -> tuple[str, HistoryEntry]:
    # 오류 조사 기록
    entry = HistoryEntry(
        step=step,
        tool=name,
        args=args,
        reason=reason,
        found=None,
        evidence_ids=[],
        error=message,
    )
    # 접두어를 붙인 메시지와 기록 반환
    return f"{TOOL_ARGUMENT_ERROR_PREFIX}{message}", entry


# 검증 오류 요약
# Pydantic 검증 오류를 "필드: 원인" 형식의 한 줄로 요약하는 함수
def _summarize(error: ValidationError) -> str:
    # 오류마다 필드 위치와 메시지 조합
    parts = []
    for item in error.errors():
        location = ".".join(str(part) for part in item["loc"]) or "입력"
        parts.append(f"{location}: {item['msg']}")
    # 세미콜론으로 합쳐 반환
    return "; ".join(parts)


# ToolMessage 생성
# 내용과 원래 도구 호출 ID를 연결한 ToolMessage를 만드는 함수
def _tool_message(content: str, tool_call: ToolCall) -> ToolMessage:
    # 도구 호출 ID·이름 연결
    return ToolMessage(
        content=content,
        tool_call_id=tool_call["id"] or "",
        name=tool_call["name"],
    )


# LLM 오류 설명
# 예외 종류와 메시지를 기록하되 API 키로 보이는 값은 가리는 함수
def _describe_error(error: Exception) -> str:
    # 예외 메시지
    message = str(error)
    # 키 패턴을 가림
    for pattern in SECRET_PATTERNS:
        message = pattern.sub(
            lambda match: (match.group(1) if match.groups() else "") + "***",
            message,
        )
    # 예외 종류와 함께 반환
    return f"{type(error).__name__}: {message}"
