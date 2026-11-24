import re
from collections.abc import Callable
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    ToolCall,
    ToolMessage,
)
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, ValidationError

from app.agent.prompts import build_report_feedback, build_report_request
from app.agent.state import (
    CollectedEvidence,
    HistoryEntry,
    InvestigationState,
    ReportError,
)
from app.agent.tool_specs import TOOL_INPUT_MODELS, get_llm_tools
from app.schemas.case import CaseFile
from app.schemas.report import FinalReport
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
REPORT_NODE = "report"
REPORT_VALIDATOR_NODE = "report_validator"

# 예산 소진 안내 문구
BUDGET_EXHAUSTED_MESSAGE = (
    "조사 예산을 모두 사용했습니다. 더 이상 도구를 호출할 수 없습니다."
)
# 도구 인자 오류 문구 접두어
TOOL_ARGUMENT_ERROR_PREFIX = "도구 인자 오류: "
# 중복 조사 기록 코드
DUPLICATE_ERROR = "duplicate"
# 미확보 증거 교차 검증 기록 코드
UNCOLLECTED_ERROR = "uncollected_evidence"
# 실행되지 않은 호출을 나타내는 기록 코드 (중복 판정 대상에서 제외)
NOT_EXECUTED_ERRORS = {DUPLICATE_ERROR, UNCOLLECTED_ERROR}

# 보고서 최대 실패 횟수 (형식 오류 포함)
MAX_REPORT_FAILURES = 2
# 강제 판단 보류 보고서
FORCED_WITHHOLD_REPORT = FinalReport(
    verdict="withhold",
    suspect_id=None,
    cited_evidence_ids=[],
    contradictions=[],
    unverified=["보고서 검증 실패로 결론을 확정하지 못했습니다."],
    explanation="최종 보고서가 2회 검증에 실패해 판단을 보류합니다.",
)

# 오류 메시지에서 가릴 API 키 패턴 (Google API 키 형식, URL의 key 파라미터)
SECRET_PATTERNS = (
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"AQ\.[0-9A-Za-z_\-]{20,}"),
    re.compile(r"(key=)[^&\s]+", re.IGNORECASE),
)


# 수사 그래프 생성
# LLM과 사건을 받아 조사 반복·최종 보고서 작성·서버 검증까지 하는 LangGraph 그래프를 컴파일해 반환하는 함수
def build_investigation_graph(llm: BaseChatModel, case: CaseFile) -> CompiledStateGraph:
    # 도구 명세를 묶은 LLM
    llm_with_tools = llm.bind_tools(get_llm_tools())
    # 최종 보고서 구조화 출력 LLM (원문·파싱 오류도 함께 받음)
    report_llm = llm.with_structured_output(FinalReport, include_raw=True)
    # 용의자 ID 목록
    suspect_ids = [suspect.id for suspect in case.suspects]

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
                "error": _describe_error(error),
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
    # 마지막 AIMessage의 도구 호출을 순서대로 처리해 ToolMessage·증거·기록을 상태에 반영하는 함수
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
            # 예산을 다 썼으면 실행·기록하지 않고 안내만 (차감 없음)
            if count >= case.tool_budget:
                content = _with_remaining(BUDGET_EXHAUSTED_MESSAGE, case, count)
                tool_messages.append(_tool_message(content, tool_call))
                continue
            # 호출 횟수 차감
            count += 1
            # 검증·중복·교차 검증 대상 확인 후 실행
            content, entry = _process_tool_call(
                case, tool_call, count, collected, history
            )
            history.append(entry)
            # 남은 예산 안내를 붙여 메시지 추가
            tool_messages.append(
                _tool_message(_with_remaining(content, case, count), tool_call)
            )

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

    # 보고서 노드
    # 확보 증거 안에서 최종 보고서를 구조화 출력으로 받아 검증 대기 상태로 저장하는 함수
    def report(state: InvestigationState) -> dict[str, Any]:
        # 이번 시도 번호 (이전 실패 시도 수 + 1)
        attempt = _failed_attempts(state["report_errors"]) + 1
        # 이번에 추가할 요청 메시지 (첫 시도는 보고서 요청, 재시도는 피드백)
        if attempt == 1:
            request = build_report_request(
                list(state["collected_evidence"]), suspect_ids
            )
        else:
            request = build_report_feedback(
                [
                    item["detail"]
                    for item in state["report_errors"]
                    if item["attempt"] == attempt - 1
                ]
            )
        new_messages: list[BaseMessage] = [HumanMessage(content=request)]

        # 구조화 출력 호출 (네트워크·API 오류면 실패 상태로 종료)
        try:
            output = report_llm.invoke([*state["messages"], *new_messages])
        except Exception as error:  # noqa: BLE001
            # 보고서 단계 오류는 실패 처리 (수사 종료 사유는 유지)
            return {
                "messages": new_messages,
                "status": "failed",
                "error": _describe_error(error),
            }

        # 원문·파싱 결과·파싱 오류 꺼내기
        raw, parsed, parsing_error = _unpack_structured_output(output)
        # 형식 오류면 parse 오류 기록 (인용 오류 횟수는 늘리지 않음)
        if parsing_error is not None or not isinstance(parsed, FinalReport):
            detail = f"보고서 형식 오류: {parsing_error or '구조화 결과 없음'}"
            new_messages.append(AIMessage(content=_raw_text(raw)))
            return {
                "messages": new_messages,
                "final_report": None,
                "report_errors": [
                    *state["report_errors"],
                    ReportError(attempt=attempt, kind="parse", detail=detail[:500]),
                ],
            }
        # 정상 파싱이면 보고서 JSON을 대화에 남기고 검증 대기 보고서로 저장
        new_messages.append(AIMessage(content=parsed.model_dump_json()))
        return {"messages": new_messages, "final_report": parsed}

    # 보고서 검증 노드
    # 보고서의 용의자·인용 증거를 사건 데이터·확보 증거와 대조해 통과·재작성·강제 보류를 정하는 함수
    def report_validator(state: InvestigationState) -> dict[str, Any]:
        # 검증 대기 보고서와 오류 기록
        candidate = state["final_report"]
        report_errors = list(state["report_errors"])
        rejections = state["validation_rejections"]
        # 형식 오류가 아니면 사건 데이터와 대조
        if candidate is not None:
            attempt = _failed_attempts(report_errors) + 1
            problems = _validate_report(candidate, case, state["collected_evidence"])
            # 문제가 없으면 통과
            if not problems:
                return {
                    "report_status": "accepted",
                    "status": (
                        "completed" if candidate.verdict == "accuse" else "inconclusive"
                    ),
                }
            # 문제가 있으면 거절 횟수 1 증가 후 오류 기록
            rejections += 1
            report_errors.extend(
                ReportError(attempt=attempt, kind=kind, detail=detail)
                for kind, detail in problems
            )
        # 누적 실패가 한도에 이르면 강제 판단 보류
        if _failed_attempts(report_errors) >= MAX_REPORT_FAILURES:
            return {
                "final_report": FORCED_WITHHOLD_REPORT,
                "report_status": "forced_withhold",
                "status": "inconclusive",
                "validation_rejections": rejections,
                "report_errors": report_errors,
            }
        # 아니면 재작성을 위해 검증 대기 보고서를 비우고 기록 갱신
        return {
            "final_report": None,
            "validation_rejections": rejections,
            "report_errors": report_errors,
        }

    # 수사관 다음 경로
    # 실패면 종료, 도구 호출이 있으면 도구 실행, 수사 종료면 보고서로 보내는 함수
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

    # 보고서 다음 경로
    # 보고서 단계에서 실패했으면 종료, 아니면 검증으로 보내는 함수
    def route_after_report(state: InvestigationState) -> str:
        # API 오류 등으로 실패면 종료
        if state["status"] == "failed":
            return END
        # 서버 검증으로 이동
        return REPORT_VALIDATOR_NODE

    # 검증 다음 경로
    # 보고서 처리가 끝났으면 종료, 아니면 보고서 재작성으로 보내는 함수
    def route_after_validator(state: InvestigationState) -> str:
        # 통과 또는 강제 판단 보류면 종료
        if state["report_status"] is not None:
            return END
        # 재작성
        return REPORT_NODE

    # 그래프 구성
    graph = StateGraph(InvestigationState)
    graph.add_node(INVESTIGATOR_NODE, investigator)
    graph.add_node(TOOL_EXECUTOR_NODE, tool_executor)
    graph.add_node(REPORT_NODE, report)
    graph.add_node(REPORT_VALIDATOR_NODE, report_validator)
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


# 도구 호출 처리
# 도구 호출 하나를 입력 검증·중복 확인·교차 검증 대상 확인 후 실행하고 메시지 내용과 기록을 반환하는 함수
def _process_tool_call(
    case: CaseFile,
    tool_call: ToolCall,
    step: int,
    collected: dict[str, CollectedEvidence],
    history: list[HistoryEntry],
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
        return _argument_error(name, record_args, reason, step, message)

    # 입력 모델로 인자 검증
    try:
        validated = input_model.model_validate(raw_args)
    except ValidationError as error:
        return _argument_error(name, record_args, reason, step, _summarize(error))

    # 검증된 인자 (reason 제외)와 정리된 이유
    call_args = validated.model_dump(exclude={"reason"})
    reason = getattr(validated, "reason", reason)

    # 중복 조사 확인 (도구까지 실행된 이전 호출과 같은 요청이면 실행하지 않음)
    duplicate_step = _find_duplicate_step(name, call_args, history)
    if duplicate_step is not None:
        message = (
            f"중복 조사: {duplicate_step}번째 호출과 같은 요청이라 실행하지 않았습니다."
        )
        return message, _history_entry(
            step, name, call_args, reason, error=DUPLICATE_ERROR
        )

    # 교차 검증 대상 확인 (확보하지 않은 증거가 있으면 실행하지 않음)
    if name == "cross_check_evidence":
        missing = [
            evidence_id
            for evidence_id in call_args["evidence_ids"]
            if evidence_id not in collected
        ]
        if missing:
            message = (
                f"확보하지 않은 증거는 교차 검증할 수 없습니다: {', '.join(missing)}"
            )
            return message, _history_entry(
                step, name, call_args, reason, error=UNCOLLECTED_ERROR
            )

    # 실제 도구 함수 호출
    try:
        result = tool_function(case, **call_args)
    except ToolArgumentError as error:
        return _argument_error(name, call_args, reason, step, str(error))

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
    # 결과 JSON과 기록 반환
    entry = _history_entry(
        step, name, call_args, reason, found=found, evidence_ids=evidence_ids
    )
    return result.model_dump_json(), entry


# 중복 호출 찾기
# 도구까지 실행된 이전 호출 중 같은 요청이 있으면 그 순번을 반환하는 함수 (없으면 None)
def _find_duplicate_step(
    name: str, call_args: dict[str, Any], history: list[HistoryEntry]
) -> int | None:
    # 이번 요청의 비교 키
    key = _request_key(name, call_args)
    # 이전 기록을 순서대로 확인
    for entry in history:
        # 도구까지 실행되지 않은 호출은 제외
        if not _was_executed(entry):
            continue
        # 같은 요청이면 그 순번 반환
        if _request_key(entry["tool"], entry["args"]) == key:
            return entry["step"]
    # 중복 없음
    return None


# 실행 여부 판정
# 기록된 호출이 입력 검증을 통과해 도구 함수까지 실행되었는지 반환하는 함수
def _was_executed(entry: HistoryEntry) -> bool:
    # 중복·미확보 차단 호출은 실행되지 않음
    if entry["error"] in NOT_EXECUTED_ERRORS:
        return False
    # 알 수 없는 도구는 실행되지 않음
    input_model = TOOL_INPUT_MODELS.get(entry["tool"])
    if input_model is None:
        return False
    # 기록된 인자와 이유로 다시 검증해 통과하면 원래 호출도 검증을 통과한 것
    try:
        input_model.model_validate({**entry["args"], "reason": entry["reason"]})
    except ValidationError:
        return False
    # 도구 함수까지 실행됨
    return True


# 요청 비교 키
# 도구 이름과 인자로 중복 비교용 키를 만드는 함수 (교차 검증 증거는 순서 무관)
def _request_key(name: str, args: dict[str, Any]) -> tuple[str, tuple[Any, ...]]:
    # 교차 검증은 증거 ID를 집합으로 비교
    if name == "cross_check_evidence":
        return name, tuple(sorted(set(args.get("evidence_ids", []))))
    # 그 외는 인자 항목을 정렬해 비교
    return name, tuple(sorted((key, str(value)) for key, value in args.items()))


# 조사 기록 생성
# 도구 호출 한 번의 기록 항목을 만드는 함수
def _history_entry(
    step: int,
    name: str,
    args: dict[str, Any],
    reason: str | None,
    *,
    found: bool | None = None,
    evidence_ids: list[str] | None = None,
    error: str | None = None,
) -> HistoryEntry:
    # 기록 항목 반환
    return HistoryEntry(
        step=step,
        tool=name,
        args=args,
        reason=reason,
        found=found,
        evidence_ids=evidence_ids or [],
        error=error,
    )


# 인자 오류 결과 생성
# 인자 오류를 ToolMessage 내용과 조사 기록으로 만드는 함수
def _argument_error(
    name: str,
    args: dict[str, Any],
    reason: str | None,
    step: int,
    message: str,
) -> tuple[str, HistoryEntry]:
    # 접두어를 붙인 메시지와 오류 기록 반환
    entry = _history_entry(step, name, args, reason, error=message)
    return f"{TOOL_ARGUMENT_ERROR_PREFIX}{message}", entry


# 남은 예산 안내 붙이기
# 메시지 끝에 줄바꿈 후 남은 조사 예산 안내를 붙이는 함수
def _with_remaining(content: str, case: CaseFile, count: int) -> str:
    # 남은 예산 (최소 0)
    remaining = max(case.tool_budget - count, 0)
    # 안내를 붙여 반환
    return f"{content}\n남은 조사 예산: {remaining}회"


# 보고서 검증
# 보고서의 용의자·인용 증거를 사건과 확보 증거에 대조해 (오류 종류, 내용) 목록을 반환하는 함수
def _validate_report(
    candidate: FinalReport,
    case: CaseFile,
    collected: dict[str, CollectedEvidence],
) -> list[tuple[Any, str]]:
    # 발견한 문제 목록
    problems: list[tuple[Any, str]] = []
    # 지목한 용의자가 사건 용의자가 아니면 오류
    suspect_ids = {suspect.id for suspect in case.suspects}
    if candidate.verdict == "accuse" and candidate.suspect_id not in suspect_ids:
        problems.append(
            (
                "invalid_suspect",
                f"사건 용의자가 아닌 ID를 지목했습니다: {candidate.suspect_id}",
            )
        )
    # 확보하지 않은 증거를 인용했으면 오류
    uncollected = [
        evidence_id
        for evidence_id in candidate.cited_evidence_ids
        if evidence_id not in collected
    ]
    if uncollected:
        problems.append(
            (
                "uncollected_evidence",
                f"확보하지 않은 증거를 인용했습니다: {', '.join(uncollected)}",
            )
        )
    # 지목인데 근거 증거가 없으면 오류
    if candidate.verdict == "accuse" and not candidate.cited_evidence_ids:
        problems.append(
            ("missing_evidence", "용의자를 지목했지만 근거 증거 ID가 없습니다.")
        )
    # 문제 목록 반환
    return problems


# 실패 시도 수
# 보고서 오류 기록에서 실패한 시도 번호의 개수를 세는 함수
def _failed_attempts(report_errors: list[ReportError]) -> int:
    # 서로 다른 시도 번호 개수 반환
    return len({item["attempt"] for item in report_errors})


# 구조화 출력 풀기
# include_raw 구조화 출력에서 원문 메시지·파싱 결과·파싱 오류를 꺼내는 함수
def _unpack_structured_output(output: Any) -> tuple[Any, Any, Any]:
    # 원문·파싱 결과·오류를 담은 dict면 각각 꺼내기
    if isinstance(output, dict):
        return output.get("raw"), output.get("parsed"), output.get("parsing_error")
    # 그 외 형태면 파싱 결과만 있는 것으로 처리
    return None, output, None


# 원문 텍스트
# 구조화 출력 원문 메시지에서 대화에 남길 텍스트를 꺼내는 함수
def _raw_text(raw: Any) -> str:
    # 원문 메시지의 텍스트 (비어 있으면 대체 문구)
    text = raw.text if isinstance(raw, AIMessage) else ""
    return text or "(보고서 형식 오류)"


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
