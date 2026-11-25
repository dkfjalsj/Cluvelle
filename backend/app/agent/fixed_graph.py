"""고정 계획형 수사 그래프.

비교 실험(평가 스크립트) 전용이다. 공개 API로는 노출하지 않으며, 서비스에서는 적응형만 쓴다.
적응형과 같은 LLM·초기 브리핑·도구·실행 규칙·보고서 검증을 쓰고, 조사 순서를 정하는 방식만 다르다.
"""

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolCall,
)
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agent.execution import describe_error, handle_tool_call
from app.agent.prompts import (
    PLANNER_SYSTEM_PROMPT,
    build_case_brief,
    build_plan_request,
)
from app.agent.report_nodes import (
    REPORT_NODE,
    REPORT_VALIDATOR_NODE,
    make_report_node,
    make_report_validator,
    route_after_report,
    route_after_validator,
    unpack_structured_output,
)
from app.agent.state import InvestigationState
from app.schemas.case import CaseFile, PublicCase
from app.schemas.plan import InvestigationPlan, PlannedStep

# 노드 이름
PLANNER_NODE = "planner"
PLAN_EXECUTOR_NODE = "plan_executor"

# 계획 형식 오류 시 최대 요청 횟수 (처음 1회 + 다시 1회)
MAX_PLAN_ATTEMPTS = 2
# 도구 인자로 옮길 계획 단계 필드
PLAN_ARG_FIELDS = ("location_id", "suspect_id", "topic_id", "camera_id", "time_window")
# 없는 값으로 볼 문자열 (공백 제거·소문자 변환 후 비교)
NULL_LIKE_VALUES = {"null", "none", ""}


# 고정 계획형 그래프 생성
# 시작 시 계획을 한 번 세우고 순서대로 실행한 뒤 보고서·검증으로 끝나는 그래프를 컴파일해 반환하는 함수
def build_fixed_graph(llm: BaseChatModel, case: CaseFile) -> CompiledStateGraph:
    # 계획 구조화 출력 LLM (원문·파싱 오류도 함께 받음)
    planner_llm = llm.with_structured_output(InvestigationPlan, include_raw=True)
    # 공개 정보만으로 만든 사건 브리핑 (적응형과 같은 함수)
    public_case = PublicCase.model_validate(case.model_dump(exclude={"evidence"}))
    brief = build_case_brief(public_case)

    # 계획 수립 노드
    # 초기 정보만으로 조사 계획을 한 번에 받아 상태에 저장하는 함수
    def planner(state: InvestigationState) -> dict[str, Any]:
        # 계획 요청 메시지 (시스템 프롬프트 + 브리핑 + 요청)
        prompt_messages: list[BaseMessage] = [
            SystemMessage(content=PLANNER_SYSTEM_PROMPT),
            HumanMessage(content=brief + "\n" + build_plan_request()),
        ]
        # 마지막 형식 오류 내용
        last_error = ""
        # 형식 오류면 1회만 다시 요청
        for _ in range(MAX_PLAN_ATTEMPTS):
            # 구조화 출력 호출 (네트워크·API 오류면 실패)
            try:
                output = planner_llm.invoke(prompt_messages)
            except Exception as error:  # noqa: BLE001
                # 계획 단계 LLM 오류는 실패 처리
                return {
                    "status": "failed",
                    "stop_reason": "llm_error",
                    "error": describe_error(error),
                }
            # 원문·파싱 결과·파싱 오류 꺼내기
            _, parsed, parsing_error = unpack_structured_output(output)
            # 정상 계획이면 저장하고 대화에 계획 JSON 남김
            if parsing_error is None and isinstance(parsed, InvestigationPlan):
                return {
                    "plan": parsed,
                    "messages": [
                        *prompt_messages,
                        AIMessage(content=parsed.model_dump_json()),
                    ],
                }
            # 형식 오류 내용 기록 후 다시 요청
            last_error = str(parsing_error or "구조화 결과 없음")
        # 2회 연속 형식 오류면 계획 실패
        return {
            "status": "failed",
            "stop_reason": "plan_error",
            "error": f"계획 형식 오류: {last_error}"[:500],
        }

    # 계획 실행 노드
    # 계획 단계를 순서대로 도구 호출로 바꿔 공통 규칙으로 처리하는 함수 (LLM 호출 없음)
    def plan_executor(state: InvestigationState) -> dict[str, Any]:
        # 실행할 계획 (planner가 성공했으므로 항상 있음)
        plan = state["plan"]
        steps = plan.steps if plan is not None else []
        # 현재 상태 복사본
        count = state["tool_call_count"]
        collected = dict(state["collected_evidence"])
        history = list(state["investigation_history"])
        new_messages: list[BaseMessage] = []
        # 계획 단계 번호 → 그 단계에서 확보된 증거 ID
        step_evidence: dict[int, list[str]] = {}

        # 계획 단계를 순서대로 처리
        for number, step in enumerate(steps, start=1):
            # 예산이 다 찼으면 남은 단계는 처리·기록하지 않음
            if count >= case.tool_budget:
                break
            # 단계를 도구 호출 인자로 변환 (교차 검증은 source_steps를 증거 ID로)
            args, preset_error = _step_to_args(step, number, step_evidence)
            tool_call = ToolCall(
                name=step.tool, args=args, id=f"plan-{number}", type="tool_call"
            )
            # 적응형과 같은 형식으로 도구 호출 메시지 추가
            new_messages.append(AIMessage(content="", tool_calls=[tool_call]))
            # 공통 규칙으로 처리
            message, count = handle_tool_call(
                case, tool_call, count, collected, history, preset_error
            )
            new_messages.append(message)
            # 이번 단계에서 확보된 증거 기록 (교차 검증 변환에 사용)
            step_evidence[number] = list(history[-1]["evidence_ids"])

        # 상태 변경분 (예산 소진 여부로 종료 사유 결정)
        return {
            "messages": new_messages,
            "tool_call_count": count,
            "collected_evidence": collected,
            "investigation_history": history,
            "stop_reason": (
                "budget_exhausted" if count >= case.tool_budget else "finished"
            ),
        }

    # 계획 수립 다음 경로
    # 계획에 실패했으면 종료, 아니면 계획 실행으로 보내는 함수
    def route_after_planner(state: InvestigationState) -> str:
        # 실패면 종료
        if state["status"] == "failed":
            return END
        # 계획 실행으로 이동
        return PLAN_EXECUTOR_NODE

    # 그래프 구성
    graph = StateGraph(InvestigationState)
    graph.add_node(PLANNER_NODE, planner)
    graph.add_node(PLAN_EXECUTOR_NODE, plan_executor)
    graph.add_node(REPORT_NODE, make_report_node(llm, case))
    graph.add_node(REPORT_VALIDATOR_NODE, make_report_validator(case))
    # 시작 → 계획 수립
    graph.add_edge(START, PLANNER_NODE)
    # 계획 수립 → 계획 실행 / 종료
    graph.add_conditional_edges(
        PLANNER_NODE, route_after_planner, [PLAN_EXECUTOR_NODE, END]
    )
    # 계획 실행 → 보고서
    graph.add_edge(PLAN_EXECUTOR_NODE, REPORT_NODE)
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


# 없는 값 판정
# 계획 인자 값이 None이거나 공백 제거·대소문자 무시 후 "null"·"none"·빈 문자열이면 True를 반환하는 함수
def _is_missing(value: str | None) -> bool:
    # None이면 없는 값
    if value is None:
        return True
    # 스키마 형식 때문에 생기는 null 표현이면 없는 값
    return value.strip().lower() in NULL_LIKE_VALUES


# 계획 단계 인자 변환
# 계획 단계를 도구 인자로 바꾸고, source_steps가 잘못되었으면 인자 오류 문구를 함께 반환하는 함수
def _step_to_args(
    step: PlannedStep, number: int, step_evidence: dict[int, list[str]]
) -> tuple[dict[str, Any], str | None]:
    # 값이 있는 인자만 옮기고 reason 추가 ("null"·"none"·빈 문자열은 없는 값으로 봄)
    args: dict[str, Any] = {
        field: getattr(step, field)
        for field in PLAN_ARG_FIELDS
        if not _is_missing(getattr(step, field))
    }
    args["reason"] = step.reason
    # 교차 검증이 아니면 그대로 반환 (source_steps는 도구 인자가 아님)
    if step.tool != "cross_check_evidence":
        return args, None

    # source_steps가 없거나 비어 있으면 인자 오류
    source_steps = step.source_steps or []
    if not source_steps:
        return {**args, "source_steps": source_steps}, "source_steps가 비어 있습니다."
    # 앞선 단계(현재 번호보다 작은 처리된 단계)를 가리키지 않는 번호가 있으면 인자 오류
    invalid = [
        source
        for source in source_steps
        if source < 1 or source >= number or source not in step_evidence
    ]
    if invalid:
        numbers = ", ".join(str(source) for source in invalid)
        return (
            {**args, "source_steps": source_steps},
            f"source_steps가 앞선 단계를 가리키지 않습니다: {numbers}",
        )
    # 가리킨 단계에서 실제로 확보된 증거를 단계 순서대로 모아 중복 제거
    evidence_ids: list[str] = []
    for source in source_steps:
        for evidence_id in step_evidence[source]:
            if evidence_id not in evidence_ids:
                evidence_ids.append(evidence_id)
    # 변환된 증거 ID를 인자로 넣어 반환
    return {**args, "evidence_ids": evidence_ids}, None
