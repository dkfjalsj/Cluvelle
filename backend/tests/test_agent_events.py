import json
from typing import Any

import pytest
from agent_fakes import (
    ScriptedChatModel,
    accuse_report,
    finish_message,
    tool_call_message,
    withhold_report,
)
from langchain_core.messages import AIMessage
from pydantic import BaseModel

from app.agent import execution
from app.agent.runner import (
    InvestigationStreamError,
    run_investigation,
    run_investigation_stream,
)
from app.schemas.api import InvestigationEvent

# 검증 대상 사건 ID
CASE_ID = "CASE-001"
# 이벤트에 나오면 안 되는 문자열 (사실 관계·정답 정보)
FORBIDDEN_TEXTS = ("facts", "culprit", "decisive", "solution", "grading_notes")


# 정답 경로 각본
# CASE-001 정답 경로 5회 조사(가설 포함)와 수사 종료 응답 목록을 만드는 함수
def solution_script() -> list[AIMessage]:
    # 단계별 도구·인자·가설
    steps = [
        ("inspect_scene", {"location_id": "L1"}, "아직 가설 없음"),
        ("inspect_scene", {"location_id": "L3"}, "창고 경로로 들어왔다"),
        (
            "check_cctv",
            {"camera_id": "C3", "time_window": "22:00-23:00"},
            "S3가 범인이다",
        ),
        ("interview_suspect", {"suspect_id": "S3", "topic_id": "T1"}, "S3가 범인이다"),
        (
            "cross_check_evidence",
            {"evidence_ids": ["E9", "E19"]},
            "S3 진술이 기록과 다르다",
        ),
    ]
    # 도구 호출 응답 + 수사 종료
    responses = [
        tool_call_message(
            name,
            {**args, "reason": f"{index}번째 이유", "hypothesis": hypothesis},
            f"c{index}",
        )
        for index, (name, args, hypothesis) in enumerate(steps, start=1)
    ]
    return [*responses, finish_message()]


# 스트리밍 실행
# 각본 모델로 스트리밍 실행해 (이벤트 목록, 최종 상태)를 반환하는 함수
def run_stream(
    model: ScriptedChatModel,
) -> tuple[list[InvestigationEvent], dict[str, Any]]:
    # 이벤트 수집
    events: list[InvestigationEvent] = []
    state = run_investigation_stream(CASE_ID, model, on_event=events.append)
    return events, dict(state)


# 정상 경로 이벤트 테스트
# 이벤트 종류·순서·번호·순번이 명세와 같고 같은 가설이면 가설 이벤트가 없는지 확인하는 함수
def test_event_sequence_for_solution_path() -> None:
    # 정답 경로 + 지목 보고서
    model = ScriptedChatModel(
        responses=solution_script(), reports=[accuse_report("S3", ["E1", "E9", "E19"])]
    )
    events, state = run_stream(model)
    # 번호는 0부터 1씩
    assert [event.id for event in events] == list(range(len(events)))
    # 종류 순서 (4번째 호출은 가설이 같아 hypothesis_updated 없음)
    assert [event.event for event in events] == [
        "tool_selected", "hypothesis_updated", "evidence_found",
        "tool_selected", "hypothesis_updated", "evidence_found",
        "tool_selected", "hypothesis_updated", "evidence_found",
        "tool_selected", "evidence_found",
        "tool_selected", "hypothesis_updated", "evidence_found",
        "finished",
    ]  # fmt: skip
    # 도구 이벤트의 순번이 조사 기록 순번과 같음
    selected = [event.data for event in events if event.event == "tool_selected"]
    found = [event.data for event in events if event.event == "evidence_found"]
    history = state["investigation_history"]
    assert [item["step"] for item in selected] == [entry["step"] for entry in history]
    assert [item["step"] for item in found] == [entry["step"] for entry in history]
    # 인자에 reason·hypothesis 없음, 이유는 따로 담김
    assert selected[0] == {
        "step": 1,
        "tool": "inspect_scene",
        "args": {"location_id": "L1"},
        "reason": "1번째 이유",
    }
    # 증거 이벤트 내용과 남은 예산
    assert found[0]["found"] is True
    assert [item["id"] for item in found[0]["evidence"]] == ["E1"]
    assert found[0]["remaining_budget"] == 9
    assert found[4]["found"] is None
    # 종료 이벤트
    assert events[-1].data == {
        "status": "completed",
        "stop_reason": "finished",
        "report_status": "accepted",
    }


# 특이사항 없음·인자 오류 이벤트 테스트
# 증거가 없는 조사와 인자 오류에도 evidence_found가 나가는지 확인하는 함수
def test_evidence_found_for_empty_and_error() -> None:
    # 특이사항 없음(L4) 후 없는 장소(L9)
    model = ScriptedChatModel(
        responses=[
            tool_call_message(
                "inspect_scene", {"location_id": "L4", "reason": "휴게실"}, "a"
            ),
            tool_call_message(
                "inspect_scene", {"location_id": "L9", "reason": "없는 곳"}, "b"
            ),
            finish_message(),
        ],
        reports=[withhold_report()],
    )
    events, _ = run_stream(model)
    found = [event.data for event in events if event.event == "evidence_found"]
    # 특이사항 없음
    assert found[0]["found"] is False
    assert found[0]["evidence"] == []
    assert found[0]["error"] is None
    # 인자 오류
    assert found[1]["found"] is None
    assert found[1]["error"] is not None
    # 같은 가설이 이어지면 가설 이벤트는 첫 번째 한 번뿐
    assert sum(event.event == "hypothesis_updated" for event in events) == 1


# 예산 초과 호출 이벤트 테스트
# 예산 소진 후 실행되지 않는 호출에는 이벤트가 나가지 않는지 확인하는 함수
def test_no_events_for_calls_beyond_budget() -> None:
    # 9번 서로 다른 심문 후 한 메시지에 호출 3개
    combos = [(s, t) for s in ("S1", "S2", "S3") for t in ("T1", "T2", "T3")]
    responses = [
        tool_call_message(
            "interview_suspect",
            {"suspect_id": s, "topic_id": t, "reason": "진술"},
            f"s{i}",
        )
        for i, (s, t) in enumerate(combos, start=1)
    ]
    responses.append(
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "inspect_scene",
                    "args": {
                        "location_id": loc,
                        "reason": "현장",
                        "hypothesis": "가설",
                    },
                    "id": f"m{index}",
                }
                for index, loc in enumerate(("L1", "L3", "L4"), start=1)
            ],
        )
    )
    model = ScriptedChatModel(responses=responses, reports=[withhold_report()])
    events, state = run_stream(model)
    # 도구 이벤트는 실행된 10건뿐
    steps = [event.data["step"] for event in events if event.event == "tool_selected"]
    assert steps == list(range(1, 11))
    assert sum(event.event == "evidence_found" for event in events) == 10
    assert state["tool_call_count"] == 10


# 그래프 예외 이벤트 테스트
# 그래프 실행 중 예외가 나면 finished 대신 error 이벤트로 끝나는지 확인하는 함수
def test_error_event_on_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    # 현장 조사 도구가 예상치 못한 예외를 내도록 교체
    def broken(*args: Any, **kwargs: Any) -> BaseModel:
        raise RuntimeError("내부 오류 AIza" + "x" * 35)

    monkeypatch.setitem(execution.TOOL_FUNCTIONS, "inspect_scene", broken)
    model = ScriptedChatModel(
        responses=[
            tool_call_message(
                "inspect_scene", {"location_id": "L1", "reason": "현장"}, "a"
            )
        ]
    )
    events: list[InvestigationEvent] = []
    # 예외가 마지막 상태와 함께 전달됨
    with pytest.raises(InvestigationStreamError) as error_info:
        run_investigation_stream(CASE_ID, model, on_event=events.append)
    # 마지막 이벤트는 error, finished 없음, 예외 메시지 본문은 없음
    assert events[-1].event == "error"
    assert events[-1].data == {
        "message": "수사 실행 중 오류가 발생했습니다. (RuntimeError)"
    }
    assert all(event.event != "finished" for event in events)
    assert error_info.value.last_state["case_id"] == CASE_ID


# 정답·사실 관계 미노출 테스트
# 모든 이벤트 JSON에 사실 관계·정답 관련 문자열이 없는지 확인하는 함수
def test_events_hide_facts_and_answers() -> None:
    # 정답 경로 실행
    model = ScriptedChatModel(
        responses=solution_script(), reports=[accuse_report("S3", ["E1", "E9", "E19"])]
    )
    events, _ = run_stream(model)
    # 모든 이벤트 데이터 직렬화 후 검사
    text = json.dumps([event.model_dump() for event in events], ensure_ascii=False)
    for word in FORBIDDEN_TEXTS:
        assert word not in text, word


# 최종 상태 동일성 테스트
# 같은 각본이면 스트리밍 실행과 기존 실행의 최종 상태가 같은지 확인하는 함수
def test_stream_matches_run_investigation() -> None:
    # 같은 각본으로 두 번 실행
    report = accuse_report("S3", ["E1", "E9", "E19"])
    plain = dict(
        run_investigation(
            CASE_ID, ScriptedChatModel(responses=solution_script(), reports=[report])
        )
    )
    _, streamed = run_stream(
        ScriptedChatModel(responses=solution_script(), reports=[report])
    )
    # 메시지 외 모든 키가 같음
    for key, value in plain.items():
        if key != "messages":
            assert value == streamed[key], key
    # 메시지는 종류·내용이 같음 (메시지 ID는 실행마다 다름)
    assert [(type(m), m.content) for m in plain["messages"]] == [
        (type(m), m.content) for m in streamed["messages"]
    ]
