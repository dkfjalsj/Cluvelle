from collections.abc import Callable
from typing import Any

import pytest
from agent_fakes import ScriptedChatModel
from langchain_core.messages import AIMessage, ToolMessage
from pydantic import BaseModel

from app.agent import graph as graph_module
from app.agent.runner import run_investigation
from app.agent.state import InvestigationState

# 검증 대상 사건 ID
CASE_ID = "CASE-001"
# 결론 메시지 문자열
CONCLUSION_TEXT = "- 지목 용의자: S3\n- 근거 증거: E1, E9, E19\n- 설명: 테스트 결론\n- 미확인 사항: 없음"
# 예산 소진 안내 문구
BUDGET_MESSAGE = "조사 예산을 모두 사용했습니다. 더 이상 도구를 호출할 수 없습니다."


# 도구 호출 메시지 생성
# 도구 호출 하나를 담은 AIMessage를 만드는 함수
def tool_call_message(name: str, args: dict[str, Any], call_id: str) -> AIMessage:
    # 도구 호출 하나짜리 AIMessage 반환
    return AIMessage(
        content="", tool_calls=[{"name": name, "args": args, "id": call_id}]
    )


# 결론 메시지 생성
# 도구 호출 없이 결론 텍스트만 담은 AIMessage를 만드는 함수
def conclusion_message() -> AIMessage:
    # 결론 텍스트 AIMessage 반환
    return AIMessage(content=CONCLUSION_TEXT)


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
# 정답 경로 5개 도구 호출 뒤 결론을 내면 완료 상태와 확보 증거·기록이 맞는지 확인하는 함수
def test_solution_path_completes() -> None:
    # 정답 경로 5개 도구 호출 + 결론
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
    responses.append(conclusion_message())
    # 수사 실행
    state = run_investigation(CASE_ID, ScriptedChatModel(responses=responses))
    # 종료 상태 확인
    assert state["status"] == "completed"
    assert state["stop_reason"] == "finished"
    assert state["tool_call_count"] == 5
    # 확보 증거 확인
    assert {"E1", "E2", "E19", "E9"} <= set(state["collected_evidence"])
    # 조사 기록 5개와 각 이유 확인
    history = state["investigation_history"]
    assert len(history) == 5
    for index, entry in enumerate(history, start=1):
        assert entry["step"] == index
        assert entry["reason"] == f"{index}번째 조사 이유"
        assert "reason" not in entry["args"]
    # 결론 텍스트 확인
    assert state["final_text"] == CONCLUSION_TEXT
    # ToolMessage 연결 확인
    assert_tool_messages_linked(state)


# 예산 종료 테스트
# 같은 조사만 반복하는 모델이 예산 10회에서 멈추고 도구가 10번 넘게 실행되지 않는지 확인하는 함수
def test_budget_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    # 현장 조사 호출 횟수 측정
    calls = count_tool_calls(monkeypatch, "inspect_scene")
    # 매번 같은 조사를 부르는 모델
    model = ScriptedChatModel(
        responses=[
            tool_call_message(
                "inspect_scene", {"location_id": "L2", "reason": "복도 확인"}, "repeat"
            )
        ],
        repeat_last=True,
    )
    # 수사 실행
    state = run_investigation(CASE_ID, model)
    # 정확히 10회에서 판단 보류로 종료
    assert state["tool_call_count"] == 10
    assert state["status"] == "inconclusive"
    assert state["stop_reason"] == "budget_exhausted"
    # 도구 함수는 정확히 10번만 실행
    assert calls[0] == 10


# 한 턴 여러 호출 테스트
# 예산이 1회 남았을 때 한 메시지의 도구 호출 3개 중 1개만 실행되는지 확인하는 함수
def test_multiple_calls_in_one_turn() -> None:
    # 9번의 단일 호출
    responses = [
        tool_call_message(
            "inspect_scene", {"location_id": "L2", "reason": "복도 확인"}, f"s{index}"
        )
        for index in range(1, 10)
    ]
    # 한 메시지에 도구 호출 3개
    responses.append(
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "inspect_scene",
                    "args": {"location_id": "L1", "reason": "실험실 확인"},
                    "id": "m1",
                },
                {
                    "name": "inspect_scene",
                    "args": {"location_id": "L3", "reason": "창고 확인"},
                    "id": "m2",
                },
                {
                    "name": "verify_alibi",
                    "args": {"suspect_id": "S3", "reason": "출입 기록 확인"},
                    "id": "m3",
                },
            ],
        )
    )
    # 수사 실행
    state = run_investigation(CASE_ID, ScriptedChatModel(responses=responses))
    # 호출 횟수 10에서 종료
    assert state["tool_call_count"] == 10
    assert state["status"] == "inconclusive"
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
    # 잘못된 장소 호출 후 결론
    responses = [
        tool_call_message(
            "inspect_scene", {"location_id": "L9", "reason": "없는 장소 확인"}, "bad"
        ),
        conclusion_message(),
    ]
    model = ScriptedChatModel(responses=responses)
    # 수사 실행
    state = run_investigation(CASE_ID, model)
    # 인자 오류 메시지와 횟수 확인
    messages = tool_messages(state)
    assert len(messages) == 1
    assert str(messages[0].content).startswith("도구 인자 오류:")
    assert state["tool_call_count"] == 1
    assert state["investigation_history"][0]["error"] is not None
    # 다음 턴이 진행되어 결론까지 완료
    assert model.call_count == 2
    assert state["status"] == "completed"


# reason 누락·공백 테스트
# reason이 없거나 공백이면 입력 검증 실패 메시지가 나오고 횟수가 차감되는지 확인하는 함수
def test_missing_or_blank_reason() -> None:
    # reason 누락 호출, 공백 reason 호출, 결론
    responses = [
        tool_call_message("inspect_scene", {"location_id": "L1"}, "no-reason"),
        tool_call_message(
            "inspect_scene", {"location_id": "L1", "reason": "   "}, "blank-reason"
        ),
        conclusion_message(),
    ]
    # 수사 실행
    state = run_investigation(CASE_ID, ScriptedChatModel(responses=responses))
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
    # 없는 도구 호출 후 결론
    responses = [
        tool_call_message("teleport", {"reason": "순간 이동"}, "unknown"),
        conclusion_message(),
    ]
    # 수사 실행
    state = run_investigation(CASE_ID, ScriptedChatModel(responses=responses))
    # 인자 오류 메시지와 횟수 확인
    messages = tool_messages(state)
    assert str(messages[0].content).startswith("도구 인자 오류:")
    assert "teleport" in str(messages[0].content)
    assert state["tool_call_count"] == 1
    assert state["status"] == "completed"


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
