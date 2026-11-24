import re
from collections.abc import Callable
from typing import Any

from langchain_core.messages import ToolCall, ToolMessage
from pydantic import BaseModel, ValidationError

from app.agent.state import CollectedEvidence, HistoryEntry
from app.agent.tool_specs import TOOL_INPUT_MODELS
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

# 오류 메시지에서 가릴 API 키 패턴 (Google API 키 형식, URL의 key 파라미터)
SECRET_PATTERNS = (
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"AQ\.[0-9A-Za-z_\-]{20,}"),
    re.compile(r"(key=)[^&\s]+", re.IGNORECASE),
)


# 도구 호출 하나 처리
# 예산 확인·차감 후 도구 호출을 처리해 ToolMessage와 차감 후 호출 횟수를 반환하는 함수
# history·collected는 제자리에서 갱신하고, preset_error가 있으면 차감 후 그 인자 오류로 처리한다
def handle_tool_call(
    case: CaseFile,
    tool_call: ToolCall,
    count: int,
    collected: dict[str, CollectedEvidence],
    history: list[HistoryEntry],
    preset_error: str | None = None,
) -> tuple[ToolMessage, int]:
    # 예산을 다 썼으면 실행·기록하지 않고 안내만 (차감 없음)
    if count >= case.tool_budget:
        content = with_remaining(BUDGET_EXHAUSTED_MESSAGE, case, count)
        return tool_message(content, tool_call), count
    # 호출 횟수 차감
    count += 1
    # 미리 정해진 인자 오류가 있으면 실행하지 않고 오류로 처리
    if preset_error is not None:
        raw_args = dict(tool_call.get("args") or {})
        reason = raw_args.get("reason")
        record_args = {key: value for key, value in raw_args.items() if key != "reason"}
        content, entry = argument_error(
            tool_call["name"],
            record_args,
            reason if isinstance(reason, str) else None,
            count,
            preset_error,
        )
    else:
        # 검증·중복·교차 검증 대상 확인 후 실행
        content, entry = process_tool_call(case, tool_call, count, collected, history)
    # 기록 추가
    history.append(entry)
    # 남은 예산 안내를 붙인 메시지와 횟수 반환
    return tool_message(with_remaining(content, case, count), tool_call), count


# 도구 호출 처리
# 도구 호출 하나를 입력 검증·중복 확인·교차 검증 대상 확인 후 실행하고 메시지 내용과 기록을 반환하는 함수
def process_tool_call(
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
        return argument_error(name, record_args, reason, step, message)

    # 입력 모델로 인자 검증
    try:
        validated = input_model.model_validate(raw_args)
    except ValidationError as error:
        return argument_error(name, record_args, reason, step, summarize(error))

    # 검증된 인자 (reason 제외)와 정리된 이유
    call_args = validated.model_dump(exclude={"reason"})
    reason = getattr(validated, "reason", reason)

    # 중복 조사 확인 (도구까지 실행된 이전 호출과 같은 요청이면 실행하지 않음)
    duplicate_step = find_duplicate_step(name, call_args, history)
    if duplicate_step is not None:
        message = (
            f"중복 조사: {duplicate_step}번째 호출과 같은 요청이라 실행하지 않았습니다."
        )
        return message, history_entry(
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
            return message, history_entry(
                step, name, call_args, reason, error=UNCOLLECTED_ERROR
            )

    # 실제 도구 함수 호출
    try:
        result = tool_function(case, **call_args)
    except ToolArgumentError as error:
        return argument_error(name, call_args, reason, step, str(error))

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
    entry = history_entry(
        step, name, call_args, reason, found=found, evidence_ids=evidence_ids
    )
    return result.model_dump_json(), entry


# 중복 호출 찾기
# 도구까지 실행된 이전 호출 중 같은 요청이 있으면 그 순번을 반환하는 함수 (없으면 None)
def find_duplicate_step(
    name: str, call_args: dict[str, Any], history: list[HistoryEntry]
) -> int | None:
    # 이번 요청의 비교 키
    key = request_key(name, call_args)
    # 이전 기록을 순서대로 확인
    for entry in history:
        # 도구까지 실행되지 않은 호출은 제외
        if not was_executed(entry):
            continue
        # 같은 요청이면 그 순번 반환
        if request_key(entry["tool"], entry["args"]) == key:
            return entry["step"]
    # 중복 없음
    return None


# 실행 여부 판정
# 기록된 호출이 입력 검증을 통과해 도구 함수까지 실행되었는지 반환하는 함수
def was_executed(entry: HistoryEntry) -> bool:
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
def request_key(name: str, args: dict[str, Any]) -> tuple[str, tuple[Any, ...]]:
    # 교차 검증은 증거 ID를 집합으로 비교
    if name == "cross_check_evidence":
        return name, tuple(sorted(set(args.get("evidence_ids", []))))
    # 그 외는 인자 항목을 정렬해 비교
    return name, tuple(sorted((key, str(value)) for key, value in args.items()))


# 조사 기록 생성
# 도구 호출 한 번의 기록 항목을 만드는 함수
def history_entry(
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
def argument_error(
    name: str,
    args: dict[str, Any],
    reason: str | None,
    step: int,
    message: str,
) -> tuple[str, HistoryEntry]:
    # 접두어를 붙인 메시지와 오류 기록 반환
    entry = history_entry(step, name, args, reason, error=message)
    return f"{TOOL_ARGUMENT_ERROR_PREFIX}{message}", entry


# 남은 예산 안내 붙이기
# 메시지 끝에 줄바꿈 후 남은 조사 예산 안내를 붙이는 함수
def with_remaining(content: str, case: CaseFile, count: int) -> str:
    # 남은 예산 (최소 0)
    remaining = max(case.tool_budget - count, 0)
    # 안내를 붙여 반환
    return f"{content}\n남은 조사 예산: {remaining}회"


# 검증 오류 요약
# Pydantic 검증 오류를 "필드: 원인" 형식의 한 줄로 요약하는 함수
def summarize(error: ValidationError) -> str:
    # 오류마다 필드 위치와 메시지 조합
    parts = []
    for item in error.errors():
        location = ".".join(str(part) for part in item["loc"]) or "입력"
        parts.append(f"{location}: {item['msg']}")
    # 세미콜론으로 합쳐 반환
    return "; ".join(parts)


# ToolMessage 생성
# 내용과 원래 도구 호출 ID를 연결한 ToolMessage를 만드는 함수
def tool_message(content: str, tool_call: ToolCall) -> ToolMessage:
    # 도구 호출 ID·이름 연결
    return ToolMessage(
        content=content,
        tool_call_id=tool_call["id"] or "",
        name=tool_call["name"],
    )


# LLM 오류 설명
# 예외 종류와 메시지를 기록하되 API 키로 보이는 값은 가리는 함수
def describe_error(error: Exception) -> str:
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
