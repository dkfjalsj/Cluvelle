import re
from typing import Any

import pytest
from agent_fakes import (
    ScriptedChatModel,
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
# 남은 예산 안내 줄 정규식
REMAINING_PATTERN = re.compile(r"^남은 조사 예산: (\d+)회$")


# 도구 메시지 목록
# 최종 상태의 메시지 중 ToolMessage만 골라 반환하는 함수
def tool_messages(state: InvestigationState) -> list[ToolMessage]:
    # ToolMessage만 반환
    return [item for item in state["messages"] if isinstance(item, ToolMessage)]


# 각본 실행
# 도구 호출 응답 목록 뒤에 수사 종료와 보류 보고서를 붙여 수사를 실행하는 함수
def run_script(responses: list[AIMessage]) -> InvestigationState:
    # 수사 종료 응답과 보고서 각본 추가
    model = ScriptedChatModel(
        responses=[*responses, finish_message()], reports=[withhold_report()]
    )
    # 수사 실행 후 상태 반환
    return run_investigation(CASE_ID, model)


# 중복 현장 조사 테스트
# 같은 현장 조사를 두 번 부르면 두 번째는 실행되지 않고 중복 메시지·횟수 차감이 맞는지 확인하는 함수
def test_duplicate_inspect_scene(monkeypatch: pytest.MonkeyPatch) -> None:
    # 현장 조사 실행 횟수 측정
    original = graph_module.TOOL_FUNCTIONS["inspect_scene"]
    calls = [0]

    # 횟수 세는 도구 함수
    # 호출 횟수를 1 늘리고 원래 도구 함수를 그대로 실행하는 함수
    def wrapper(*args: Any, **kwargs: Any) -> BaseModel:
        # 호출 횟수 증가 후 원래 함수 실행
        calls[0] += 1
        return original(*args, **kwargs)

    monkeypatch.setitem(graph_module.TOOL_FUNCTIONS, "inspect_scene", wrapper)
    # 같은 조사 2회 (reason은 달라도 중복)
    state = run_script(
        [
            tool_call_message(
                "inspect_scene",
                {"location_id": "L1", "reason": "첫 확인", "hypothesis": "테스트 가설"},
                "a",
            ),
            tool_call_message(
                "inspect_scene",
                {
                    "location_id": "L1",
                    "reason": "다시 확인",
                    "hypothesis": "테스트 가설",
                },
                "b",
            ),
        ]
    )
    # 두 번째 메시지는 중복 안내
    messages = tool_messages(state)
    assert str(messages[1].content).startswith(
        "중복 조사: 1번째 호출과 같은 요청이라 실행하지 않았습니다."
    )
    # 횟수는 2, 도구 함수는 1회만 실행
    assert state["tool_call_count"] == 2
    assert calls[0] == 1
    # 기록에 중복 코드
    assert state["investigation_history"][1]["error"] == "duplicate"


# 같은 턴 중복 테스트
# 한 메시지 안의 동일한 도구 호출 2개 중 두 번째가 중복으로 처리되는지 확인하는 함수
def test_duplicate_in_same_turn() -> None:
    # 같은 호출 2개를 한 메시지에
    same_turn = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "verify_alibi",
                "args": {
                    "suspect_id": "S3",
                    "reason": "기록 확인",
                    "hypothesis": "테스트 가설",
                },
                "id": "x1",
            },
            {
                "name": "verify_alibi",
                "args": {
                    "suspect_id": "S3",
                    "reason": "기록 재확인",
                    "hypothesis": "테스트 가설",
                },
                "id": "x2",
            },
        ],
    )
    # 수사 실행
    state = run_script([same_turn])
    # 두 번째는 중복 처리
    messages = tool_messages(state)
    assert str(messages[1].content).startswith("중복 조사: 1번째 호출")
    assert state["investigation_history"][1]["error"] == "duplicate"
    assert state["tool_call_count"] == 2


# 교차 검증 순서 무관 중복 테스트
# 같은 증거를 순서만 바꿔 교차 검증하면 중복으로 처리되는지 확인하는 함수
def test_cross_check_order_duplicate() -> None:
    # E9·E19 확보 후 교차 검증 2회 (순서 반대)
    state = run_script(
        [
            tool_call_message(
                "interview_suspect",
                {
                    "suspect_id": "S3",
                    "topic_id": "T1",
                    "reason": "동선 확인",
                    "hypothesis": "테스트 가설",
                },
                "a",
            ),
            tool_call_message(
                "check_cctv",
                {
                    "camera_id": "C3",
                    "time_window": "22:00-23:00",
                    "reason": "주차장",
                    "hypothesis": "테스트 가설",
                },
                "b",
            ),
            tool_call_message(
                "cross_check_evidence",
                {
                    "evidence_ids": ["E9", "E19"],
                    "reason": "비교",
                    "hypothesis": "테스트 가설",
                },
                "c",
            ),
            tool_call_message(
                "cross_check_evidence",
                {
                    "evidence_ids": ["E19", "E9"],
                    "reason": "다시 비교",
                    "hypothesis": "테스트 가설",
                },
                "d",
            ),
        ]
    )
    # 네 번째 호출은 3번째 호출의 중복
    messages = tool_messages(state)
    assert str(messages[3].content).startswith("중복 조사: 3번째 호출")
    assert state["investigation_history"][3]["error"] == "duplicate"


# 미확보 증거 교차 검증 테스트
# 확보하지 않은 증거가 있으면 교차 검증이 실행되지 않고, 확보 후에는 실행되는지 확인하는 함수
def test_cross_check_requires_collected_evidence() -> None:
    # E9만 확보한 상태에서 교차 검증 → E19 확보 → 같은 교차 검증 재시도
    state = run_script(
        [
            tool_call_message(
                "interview_suspect",
                {
                    "suspect_id": "S3",
                    "topic_id": "T1",
                    "reason": "동선 확인",
                    "hypothesis": "테스트 가설",
                },
                "a",
            ),
            tool_call_message(
                "cross_check_evidence",
                {
                    "evidence_ids": ["E9", "E19"],
                    "reason": "비교",
                    "hypothesis": "테스트 가설",
                },
                "b",
            ),
            tool_call_message(
                "check_cctv",
                {
                    "camera_id": "C3",
                    "time_window": "22:00-23:00",
                    "reason": "주차장",
                    "hypothesis": "테스트 가설",
                },
                "c",
            ),
            tool_call_message(
                "cross_check_evidence",
                {
                    "evidence_ids": ["E9", "E19"],
                    "reason": "확보 후 비교",
                    "hypothesis": "테스트 가설",
                },
                "d",
            ),
        ]
    )
    messages = tool_messages(state)
    history = state["investigation_history"]
    # 미확보 상태의 교차 검증은 미실행, 횟수는 차감
    assert str(messages[1].content).startswith(
        "확보하지 않은 증거는 교차 검증할 수 없습니다: E19"
    )
    assert history[1]["error"] == "uncollected_evidence"
    # 확보 후 교차 검증은 실행 (중복으로 막히지 않음)
    assert history[3]["error"] is None
    assert '"tool":"cross_check_evidence"' in str(messages[3].content)
    assert state["tool_call_count"] == 4


# 남은 예산 안내 테스트
# 모든 ToolMessage 마지막 줄이 남은 조사 예산 안내이고 값이 정확한지 확인하는 함수
def test_remaining_budget_line_on_every_message() -> None:
    # 성공·오류·중복을 섞고 마지막에 예산을 넘는 호출 포함
    calls = [
        ("inspect_scene", {"location_id": "L1"}),
        ("inspect_scene", {"location_id": "L9"}),
        ("inspect_scene", {"location_id": "L1"}),
        ("inspect_scene", {"location_id": "L2"}),
        ("inspect_scene", {"location_id": "L3"}),
        ("inspect_scene", {"location_id": "L4"}),
        ("inspect_scene", {"location_id": "L5"}),
        ("inspect_scene", {"location_id": "L6"}),
        ("verify_alibi", {"suspect_id": "S1"}),
    ]
    responses = [
        tool_call_message(
            name, {**args, "reason": "확인", "hypothesis": "테스트 가설"}, f"r{index}"
        )
        for index, (name, args) in enumerate(calls, start=1)
    ]
    # 남은 1회에 호출 2개를 보내 하나는 예산 소진 안내가 되게 함
    responses.append(
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "verify_alibi",
                    "args": {
                        "suspect_id": "S2",
                        "reason": "확인",
                        "hypothesis": "테스트 가설",
                    },
                    "id": "last1",
                },
                {
                    "name": "verify_alibi",
                    "args": {
                        "suspect_id": "S3",
                        "reason": "확인",
                        "hypothesis": "테스트 가설",
                    },
                    "id": "last2",
                },
            ],
        )
    )
    model = ScriptedChatModel(responses=responses, reports=[withhold_report()])
    state = run_investigation(CASE_ID, model)
    # 메시지마다 마지막 줄 확인
    messages = tool_messages(state)
    expected = [9, 8, 7, 6, 5, 4, 3, 2, 1, 0, 0]
    assert len(messages) == len(expected)
    for message, remaining in zip(messages, expected, strict=True):
        last_line = str(message.content).splitlines()[-1]
        match = REMAINING_PATTERN.match(last_line)
        assert match is not None, last_line
        assert int(match.group(1)) == remaining
    # 마지막 메시지는 예산 소진 안내
    assert str(messages[-1].content).startswith("조사 예산을 모두 사용했습니다.")
