import json

from agent_fakes import (
    ScriptedChatModel,
    finish_message,
    tool_call_message,
    withhold_report,
)
from api_helpers import api_client, read_sse
from langchain_core.messages import AIMessage, HumanMessage

from app.agent.runner import run_investigation, run_investigation_stream
from app.api.investigations import get_run_store
from app.schemas.api import InvestigationEvent
from app.schemas.plan import InvestigationPlan, PlannedStep
from app.services.investigation_runs import InvestigationRunStore

# 검증 대상 사건 ID
CASE_ID = "CASE-001"
# 재촉 문구의 앞부분
NUDGE_PREFIX = "아직 조사 예산이"


# 서로 다른 조사 10개
# CASE-001에서 서로 겹치지 않는 도구 호출 10개를 순서대로 만드는 함수
def distinct_calls() -> list[AIMessage]:
    # 현장 조사 6곳 + 알리바이 3명 + 심문 1건
    specs = [("inspect_scene", {"location_id": f"L{n}"}) for n in range(1, 7)]
    specs += [("verify_alibi", {"suspect_id": f"S{n}"}) for n in range(1, 4)]
    specs.append(("interview_suspect", {"suspect_id": "S3", "topic_id": "T1"}))
    # 도구 호출 메시지 목록
    return [
        tool_call_message(name, {**args, "reason": "조사"}, f"c{index}")
        for index, (name, args) in enumerate(specs, start=1)
    ]


# 재촉 메시지 목록
# 상태의 메시지 중 재촉 문구로 시작하는 사용자 메시지만 골라 반환하는 함수
def nudges(state: dict[str, object]) -> list[HumanMessage]:
    # 재촉 사용자 메시지만
    messages = state["messages"]
    assert isinstance(messages, list)
    return [
        message
        for message in messages
        if isinstance(message, HumanMessage)
        and str(message.content).startswith(NUDGE_PREFIX)
    ]


# 기본값 동작 테스트
# 기본값(False)이면 도구 호출 없이 끝낼 때 재촉 없이 바로 보고서로 가는지 확인하는 함수
def test_default_goes_to_report_without_nudge() -> None:
    # 조사 3회 후 수사 종료
    model = ScriptedChatModel(
        responses=[*distinct_calls()[:3], finish_message()],
        reports=[withhold_report()],
    )
    state = dict(run_investigation(CASE_ID, model))
    # 재촉 없이 보고서
    assert nudges(state) == []
    assert state["tool_call_count"] == 3
    assert state["stop_reason"] == "finished"
    assert model.call_count == 4
    assert state["nudge_streak"] == 0


# 재촉 후 계속 조사 테스트
# 예산 모두 사용 모드에서 3회 후 끝내려 하면 재촉받고 조사를 이어 10회에서 보고서로 가는지 확인하는 함수
def test_nudge_then_continue_to_full_budget() -> None:
    # 조사 3회 → 종료 시도 → 조사 7회
    calls = distinct_calls()
    model = ScriptedChatModel(
        responses=[*calls[:3], finish_message(), *calls[3:]],
        reports=[withhold_report()],
    )
    state = dict(run_investigation(CASE_ID, model, use_full_budget=True))
    # 재촉 1회, 남은 예산 7회 문구, 10회 소진 후 보고서
    found = nudges(state)
    assert len(found) == 1
    assert str(found[0].content) == (
        "아직 조사 예산이 7회 남았다. 결론을 내리기 전에 아직 확인하지 않은 조사를 "
        "더 하라. 이미 한 조사를 반복하면 예산만 쓰인다."
    )
    assert state["tool_call_count"] == 10
    assert state["stop_reason"] == "budget_exhausted"
    assert state["report_status"] == "accepted"
    # 도구 호출 뒤 연속 재촉 횟수는 0으로 초기화
    assert state["nudge_streak"] == 0


# 연속 재촉 상한 테스트
# 재촉에도 연속으로 도구 호출이 없으면 3회 재촉 뒤 예산이 남아도 보고서로 가는지 확인하는 함수
def test_nudge_limit_goes_to_report() -> None:
    # 조사 3회 후 계속 종료만 시도
    model = ScriptedChatModel(
        responses=[*distinct_calls()[:3], finish_message()],
        repeat_last=True,
        reports=[withhold_report()],
    )
    state = dict(run_investigation(CASE_ID, model, use_full_budget=True))
    # 재촉 3회, 도구 없는 응답 4회, 예산 남은 채 보고서
    assert len(nudges(state)) == 3
    assert model.call_count == 3 + 4
    assert state["tool_call_count"] == 3
    assert state["stop_reason"] == "finished"
    assert state["nudge_streak"] == 3
    assert state["final_report"] is not None


# 재촉 비노출 테스트
# 재촉 메시지가 SSE 이벤트와 조사 기록에 나오지 않는지 확인하는 함수
def test_nudge_hidden_from_events_and_history() -> None:
    # 조사 3회 → 종료 시도 → 조사 7회
    calls = distinct_calls()
    model = ScriptedChatModel(
        responses=[*calls[:3], finish_message(), *calls[3:]],
        reports=[withhold_report()],
    )
    events: list[InvestigationEvent] = []
    state = dict(
        run_investigation_stream(
            CASE_ID, model, on_event=events.append, use_full_budget=True
        )
    )
    # 이벤트 문자열에 재촉 문구 없음, 도구 이벤트는 10건
    text = json.dumps([event.model_dump() for event in events], ensure_ascii=False)
    assert NUDGE_PREFIX not in text
    assert sum(event.event == "tool_selected" for event in events) == 10
    # 조사 기록은 도구 호출 10건뿐
    history = state["investigation_history"]
    assert isinstance(history, list)
    assert len(history) == 10
    assert NUDGE_PREFIX not in json.dumps(history, ensure_ascii=False)


# API 설정 테스트
# 수사 시작 API가 쓰는 실행 저장소가 예산 모두 사용 모드인지 확인하는 함수
def test_api_store_uses_full_budget() -> None:
    # 실제 의존성 함수가 만드는 저장소
    get_run_store.cache_clear()
    try:
        assert get_run_store().use_full_budget is True
    finally:
        get_run_store.cache_clear()
    # 저장소 기본값은 False (CLI·평가와 같은 동작)
    assert InvestigationRunStore().use_full_budget is False


# API 수사 재촉 테스트
# 예산 모두 사용 저장소로 API 수사를 하면 일찍 끝내려 해도 조사가 이어지는지 확인하는 함수
def test_api_investigation_continues_after_nudge() -> None:
    # 조사 3회 → 종료 시도 → 조사 7회 각본
    calls = distinct_calls()

    # 각본 모델 생성
    # 호출할 때마다 같은 각본의 새 모델을 만드는 함수
    def factory() -> ScriptedChatModel:
        # 새 각본 모델 반환
        return ScriptedChatModel(
            responses=[*calls[:3], finish_message(), *calls[3:]],
            reports=[withhold_report()],
        )

    store = InvestigationRunStore(use_full_budget=True)
    with api_client(store=store, model_factory=factory) as client:
        run_id = client.post("/api/investigations", json={"case_id": CASE_ID}).json()[
            "investigation_id"
        ]
        _, events = read_sse(client, f"/api/investigations/{run_id}/events")
        result = client.get(f"/api/investigations/{run_id}/result").json()
    # 10회까지 조사하고 끝남
    assert result["tool_call_count"] == 10
    assert events[-1]["event"] == "finished"
    assert events[-1]["data"]["stop_reason"] == "budget_exhausted"


# 고정 계획형 무관 테스트
# 고정 계획형은 예산 모두 사용 옵션을 줘도 결과가 같은지 확인하는 함수
def test_fixed_mode_ignores_full_budget() -> None:
    # 1단계 계획 각본
    plan = InvestigationPlan(
        steps=[PlannedStep(tool="inspect_scene", location_id="L1", reason="현장")],
        rationale="테스트",
    )
    # 옵션 없이·있이 각각 실행
    plain = dict(
        run_investigation(
            CASE_ID,
            ScriptedChatModel(plans=[plan], reports=[withhold_report()]),
            mode="fixed",
        )
    )
    flagged = dict(
        run_investigation(
            CASE_ID,
            ScriptedChatModel(plans=[plan], reports=[withhold_report()]),
            mode="fixed",
            use_full_budget=True,
        )
    )
    # 메시지 외 결과가 같음
    for key, value in plain.items():
        if key != "messages":
            assert value == flagged[key], key
