from collections.abc import Callable
from typing import Any

import pytest
from agent_fakes import (
    ScriptedChatModel,
    accuse_report,
    finish_message,
    tool_call_message,
    withhold_report,
)
from langchain_core.messages import AIMessage, ToolMessage
from pydantic import BaseModel

from app.agent import graph as graph_module
from app.agent.runner import run_investigation
from app.agent.state import InvestigationState

# 검증 대상 사건 ID
CASE_ID = "CASE-001"
# 예산 소진 안내 문구 (남은 예산 0 안내 포함)
BUDGET_MESSAGE = (
    "조사 예산을 모두 사용했습니다. 더 이상 도구를 호출할 수 없습니다.\n"
    "남은 조사 예산: 0회"
)


# 도구 메시지 목록
# 최종 상태의 메시지 중 ToolMessage만 골라 반환하는 함수
def tool_messages(state: InvestigationState) -> list[ToolMessage]:
    # ToolMessage만 반환
    return [item for item in state["messages"] if isinstance(item, ToolMessage)]


# 도구 함수 호출 횟수 측정
# 지정한 도구 함수를 호출 횟수를 세는 함수로 바꾸고 횟수 목록을 반환하는 함수
def count_tool_calls(monkeypatch: pytest.MonkeyPatch, name: str) -> list[int]:
    # 원래 도구 함수와 호출 횟수 저장소
    original = graph_module.TOOL_FUNCTIONS[name]
    calls = [0]

    # 횟수 세는 도구 함수
    # 호출 횟수를 1 늘리고 원래 도구 함수를 그대로 실행하는 함수
    def wrapper(*args: Any, **kwargs: Any) -> BaseModel:
        # 호출 횟수 증가 후 원래 함수 실행
        calls[0] += 1
        return original(*args, **kwargs)

    # 도구 함수 교체
    wrapped: Callable[..., BaseModel] = wrapper
    monkeypatch.setitem(graph_module.TOOL_FUNCTIONS, name, wrapped)
    # 횟수 목록 반환
    return calls


# ToolMessage 연결 확인
# 모든 ToolMessage가 바로 앞 AIMessage의 도구 호출 ID와 순서대로 연결되는지 확인하는 함수
def assert_tool_messages_linked(state: InvestigationState) -> None:
    # 아직 응답을 받지 못한 도구 호출 ID 목록
    pending: list[str] = []
    # 메시지를 순서대로 확인
    for message in state["messages"]:
        if isinstance(message, AIMessage) and message.tool_calls:
            # 이전 호출에 모두 응답했는지 확인 후 새 호출 ID 등록
            assert pending == []
            pending = [str(call["id"]) for call in message.tool_calls]
        elif isinstance(message, ToolMessage):
            # 다음 차례의 도구 호출 ID와 일치해야 함
            assert pending, "연결할 도구 호출이 없습니다."
            assert message.tool_call_id == pending.pop(0)
    # 마지막 호출까지 모두 응답했는지 확인
    assert pending == []


# 정상 경로 테스트
# 정답 경로 5회 조사 뒤 지목 보고서를 내면 완료·통과 상태와 확보 증거·기록이 맞는지 확인하는 함수
def test_solution_path_completes() -> None:
    # 정답 경로 5개 도구 호출 + 수사 종료
    steps = [
        ("inspect_scene", {"location_id": "L1"}),
        ("inspect_scene", {"location_id": "L3"}),
        ("check_cctv", {"camera_id": "C3", "time_window": "22:00-23:00"}),
        ("interview_suspect", {"suspect_id": "S3", "topic_id": "T1"}),
        ("cross_check_evidence", {"evidence_ids": ["E9", "E19"]}),
    ]
    responses = [
        tool_call_message(
            name, {**args, "reason": f"{index}번째 조사 이유"}, f"c{index}"
        )
        for index, (name, args) in enumerate(steps, start=1)
    ]
    responses.append(finish_message())
    # 지목 보고서 각본
    report = accuse_report("S3", ["E1", "E9", "E19"])
    model = ScriptedChatModel(responses=responses, reports=[report])
    # 수사 실행
    state = run_investigation(CASE_ID, model)
    # 종료 상태 확인
    assert state["status"] == "completed"
    assert state["stop_reason"] == "finished"
    assert state["report_status"] == "accepted"
    assert state["validation_rejections"] == 0
    assert state["tool_call_count"] == 5
    assert state["final_report"] == report
    # 확보 증거 확인
    assert {"E1", "E2", "E19", "E9"} <= set(state["collected_evidence"])
    # 조사 기록 5개와 각 이유 확인
    history = state["investigation_history"]
    assert len(history) == 5
    for index, entry in enumerate(history, start=1):
        assert entry["step"] == index
        assert entry["reason"] == f"{index}번째 조사 이유"
        assert "reason" not in entry["args"]
        assert entry["error"] is None
    # ToolMessage 연결 확인
    assert_tool_messages_linked(state)


# 예산 종료 테스트
# 예산 10회를 다 쓰면 수사가 멈추고 보고서 노드가 실행되어 보고서가 남는지 확인하는 함수
def test_budget_exhausted_still_reports(monkeypatch: pytest.MonkeyPatch) -> None:
    # 현장 조사 호출 횟수 측정
    calls = count_tool_calls(monkeypatch, "inspect_scene")
    # 매번 같은 조사를 부르는 모델 + 판단 보류 보고서
    model = ScriptedChatModel(
        responses=[
            tool_call_message(
                "inspect_scene",
                {
                    "location_id": "L2",
                    "reason": "복도 확인",
                    "hypothesis": "테스트 가설",
                },
                "repeat",
            )
        ],
        repeat_last=True,
        reports=[withhold_report()],
    )
    # 수사 실행
    state = run_investigation(CASE_ID, model)
    # 정확히 10회에서 수사 종료
    assert state["tool_call_count"] == 10
    assert state["stop_reason"] == "budget_exhausted"
    # 도구 함수는 10번을 넘지 않음 (반복 호출은 중복으로 차단)
    assert calls[0] <= 10
    # 보고서 노드가 실행되어 보고서가 남음
    assert model.report_call_count == 1
    assert state["final_report"] is not None
    assert state["report_status"] == "accepted"
    assert state["status"] == "inconclusive"


# 한 턴 여러 호출 테스트
# 예산이 1회 남았을 때 한 메시지의 도구 호출 3개 중 1개만 실행되는지 확인하는 함수
def test_multiple_calls_in_one_turn() -> None:
    # 9번의 서로 다른 단일 호출 (용의자×주제 조합)
    combos = [(s, t) for s in ("S1", "S2", "S3") for t in ("T1", "T2", "T3")]
    responses = [
        tool_call_message(
            "interview_suspect",
            {
                "suspect_id": s,
                "topic_id": t,
                "reason": "진술 확인",
                "hypothesis": "테스트 가설",
            },
            f"s{index}",
        )
        for index, (s, t) in enumerate(combos, start=1)
    ]
    # 한 메시지에 도구 호출 3개
    responses.append(
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "inspect_scene",
                    "args": {
                        "location_id": "L1",
                        "reason": "실험실 확인",
                        "hypothesis": "테스트 가설",
                    },
                    "id": "m1",
                },
                {
                    "name": "inspect_scene",
                    "args": {
                        "location_id": "L3",
                        "reason": "창고 확인",
                        "hypothesis": "테스트 가설",
                    },
                    "id": "m2",
                },
                {
                    "name": "verify_alibi",
                    "args": {
                        "suspect_id": "S3",
                        "reason": "출입 기록 확인",
                        "hypothesis": "테스트 가설",
                    },
                    "id": "m3",
                },
            ],
        )
    )
    model = ScriptedChatModel(responses=responses, reports=[withhold_report()])
    # 수사 실행
    state = run_investigation(CASE_ID, model)
    # 호출 횟수 10에서 종료
    assert state["tool_call_count"] == 10
    assert state["stop_reason"] == "budget_exhausted"
    # 마지막 ToolMessage 3개: 1개 실행, 2개 예산 소진 안내
    last_three = tool_messages(state)[-3:]
    assert [item.tool_call_id for item in last_three] == ["m1", "m2", "m3"]
    assert last_three[0].content != BUDGET_MESSAGE
    assert last_three[1].content == BUDGET_MESSAGE
    assert last_three[2].content == BUDGET_MESSAGE
    # 실행된 호출만 기록됨
    assert len(state["investigation_history"]) == 10
    # ToolMessage 연결 확인
    assert_tool_messages_linked(state)


# 잘못된 인자 테스트
# 없는 장소를 부르면 인자 오류 메시지가 나오고 횟수가 차감된 뒤 다음 턴이 진행되는지 확인하는 함수
def test_invalid_argument_continues() -> None:
    # 잘못된 장소 호출 후 수사 종료
    responses = [
        tool_call_message(
            "inspect_scene",
            {
                "location_id": "L9",
                "reason": "없는 장소 확인",
                "hypothesis": "테스트 가설",
            },
            "bad",
        ),
        finish_message(),
    ]
    model = ScriptedChatModel(responses=responses, reports=[withhold_report()])
    # 수사 실행
    state = run_investigation(CASE_ID, model)
    # 인자 오류 메시지와 횟수 확인
    messages = tool_messages(state)
    assert len(messages) == 1
    assert str(messages[0].content).startswith("도구 인자 오류:")
    assert state["tool_call_count"] == 1
    assert state["investigation_history"][0]["error"] is not None
    # 다음 턴이 진행되어 보고서까지 작성
    assert model.call_count == 2
    assert state["report_status"] == "accepted"


# reason 누락·공백 테스트
# reason이 없거나 공백이면 입력 검증 실패 메시지가 나오고 횟수가 차감되는지 확인하는 함수
def test_missing_or_blank_reason() -> None:
    # reason 누락 호출, 공백 reason 호출, 수사 종료
    responses = [
        tool_call_message("inspect_scene", {"location_id": "L1"}, "no-reason"),
        tool_call_message(
            "inspect_scene",
            {"location_id": "L1", "reason": "   ", "hypothesis": "테스트 가설"},
            "blank-reason",
        ),
        finish_message(),
    ]
    model = ScriptedChatModel(responses=responses, reports=[withhold_report()])
    # 수사 실행
    state = run_investigation(CASE_ID, model)
    # 두 호출 모두 인자 오류이고 reason 관련 원인 포함
    messages = tool_messages(state)
    assert len(messages) == 2
    for message in messages:
        assert str(message.content).startswith("도구 인자 오류:")
        assert "reason" in str(message.content)
    # 두 번 모두 차감, 증거는 확보되지 않음
    assert state["tool_call_count"] == 2
    assert state["collected_evidence"] == {}


# 알 수 없는 도구 테스트
# 없는 도구 이름을 부르면 인자 오류로 처리되고 횟수가 차감되는지 확인하는 함수
def test_unknown_tool_name() -> None:
    # 없는 도구 호출 후 수사 종료
    responses = [
        tool_call_message(
            "teleport", {"reason": "순간 이동", "hypothesis": "테스트 가설"}, "unknown"
        ),
        finish_message(),
    ]
    model = ScriptedChatModel(responses=responses, reports=[withhold_report()])
    # 수사 실행
    state = run_investigation(CASE_ID, model)
    # 인자 오류 메시지와 횟수 확인
    messages = tool_messages(state)
    assert str(messages[0].content).startswith("도구 인자 오류:")
    assert "teleport" in str(messages[0].content)
    assert state["tool_call_count"] == 1


# LLM 예외 테스트
# LLM 호출이 예외를 던지면 실패 상태와 오류가 기록되는지 확인하는 함수
def test_llm_error_fails() -> None:
    # 항상 예외를 던지는 모델
    model = ScriptedChatModel(error=RuntimeError("모델 연결 실패"))
    # 수사 실행
    state = run_investigation(CASE_ID, model)
    # 실패 상태와 오류 확인
    assert state["status"] == "failed"
    assert state["stop_reason"] == "llm_error"
    assert state["error"] is not None
    assert "RuntimeError" in state["error"]
    assert state["tool_call_count"] == 0
    assert state["final_report"] is None


# LLM 오류 키 가림 테스트
# 예외 메시지에 API 키로 보이는 값이 있으면 오류 기록에서 가려지는지 확인하는 함수
def test_llm_error_hides_key_like_values() -> None:
    # 키 형식 문자열이 들어간 예외
    fake_key = "AIza" + "x" * 35
    model = ScriptedChatModel(error=RuntimeError(f"요청 실패 key={fake_key}"))
    # 수사 실행
    state = run_investigation(CASE_ID, model)
    # 키 값이 기록에 남지 않아야 함
    assert state["error"] is not None
    assert fake_key not in state["error"]
