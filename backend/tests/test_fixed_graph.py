import re
from typing import Any, get_args

from agent_fakes import (
    ScriptedChatModel,
    accuse_report,
    finish_message,
    withhold_report,
)
from langchain_core.messages import HumanMessage, ToolMessage

from app.agent.prompts import build_plan_request
from app.agent.runner import run_investigation
from app.agent.state import InvestigationState
from app.agent.tool_specs import get_llm_tools
from app.schemas.plan import InvestigationPlan, PlannedStep

# 검증 대상 사건 ID
CASE_ID = "CASE-001"
# 남은 예산 안내 줄 정규식
REMAINING_PATTERN = re.compile(r"^남은 조사 예산: (\d+)회$")
# 형식 오류를 일으키는 계획 값 (단계가 비어 있음)
MALFORMED_PLAN: dict[str, Any] = {"steps": [], "rationale": "빈 계획"}


# 계획 단계 생성
# 도구 이름과 인자로 계획 단계 하나를 만드는 함수
def step(tool: Any, **kwargs: Any) -> PlannedStep:
    # 이유를 붙여 계획 단계 반환
    return PlannedStep(tool=tool, reason=f"{tool} 계획 이유", **kwargs)


# 계획 생성
# 계획 단계 목록으로 조사 계획을 만드는 함수
def make_plan(steps: list[PlannedStep]) -> InvestigationPlan:
    # 테스트용 의도 문장과 함께 반환
    return InvestigationPlan(steps=steps, rationale="테스트 계획 의도")


# 정답 경로 계획
# CASE-001 정답 경로 5단계 계획을 반환하는 함수
def solution_plan() -> InvestigationPlan:
    # 현장 2곳, CCTV, 심문, 교차 검증(3·4단계 증거)
    return make_plan(
        [
            step("inspect_scene", location_id="L1"),
            step("inspect_scene", location_id="L3"),
            step("check_cctv", camera_id="C3", time_window="22:00-23:00"),
            step("interview_suspect", suspect_id="S3", topic_id="T1"),
            step("cross_check_evidence", source_steps=[3, 4]),
        ]
    )


# 고정 계획형 실행
# 계획·보고서 각본으로 고정 계획형 수사를 실행해 상태와 모델을 반환하는 함수
def run_fixed(
    plans: list[Any], reports: list[Any] | None = None
) -> tuple[InvestigationState, ScriptedChatModel]:
    # 각본 모델 생성 (보고서 기본값은 판단 보류)
    model = ScriptedChatModel(
        plans=plans, reports=reports if reports is not None else [withhold_report()]
    )
    # 고정 계획형으로 실행
    state = run_investigation(CASE_ID, model, mode="fixed")
    return state, model


# 도구 메시지 목록
# 최종 상태의 메시지 중 ToolMessage만 골라 반환하는 함수
def tool_messages(state: InvestigationState) -> list[ToolMessage]:
    # ToolMessage만 반환
    return [item for item in state["messages"] if isinstance(item, ToolMessage)]


# 정상 계획 테스트
# 정답 경로 계획이 5단계 실행되고 교차 검증 증거가 변환되며 보고서가 통과하는지 확인하는 함수
def test_solution_plan_completes() -> None:
    # 정답 경로 계획 + 지목 보고서
    state, model = run_fixed(
        [solution_plan()], [accuse_report("S3", ["E1", "E9", "E19"])]
    )
    # 5단계 실행과 교차 검증 증거 변환 확인
    history = state["investigation_history"]
    assert len(history) == 5
    assert history[4]["tool"] == "cross_check_evidence"
    assert history[4]["args"]["evidence_ids"] == ["E19", "E9"]
    assert history[4]["error"] is None
    # 보고서 통과와 완료 상태
    assert state["mode"] == "fixed"
    assert state["status"] == "completed"
    assert state["report_status"] == "accepted"
    assert state["stop_reason"] == "finished"
    assert state["plan"] == solution_plan()
    # 계획 LLM 호출 1회, 수사 중 LLM 호출 없음
    assert model.plan_call_count == 1
    assert model.call_count == 0


# ToolMessage 형식 테스트
# 모든 계획 단계 ToolMessage 끝에 남은 예산 줄이 있고 tool_call_id가 plan-{n}인지 확인하는 함수
def test_tool_message_format() -> None:
    # 정답 경로 계획 실행
    state, _ = run_fixed([solution_plan()], [accuse_report("S3", ["E1", "E9", "E19"])])
    messages = tool_messages(state)
    # 단계마다 ID와 남은 예산 확인
    assert [item.tool_call_id for item in messages] == [
        f"plan-{number}" for number in range(1, 6)
    ]
    for number, message in enumerate(messages, start=1):
        match = REMAINING_PATTERN.match(str(message.content).splitlines()[-1])
        assert match is not None
        assert int(match.group(1)) == 10 - number


# 예산 초과 계획 테스트
# 12단계 계획이면 10단계만 실행하고 예산 소진 후에도 보고서를 작성하는지 확인하는 함수
def test_plan_longer_than_budget() -> None:
    # 서로 다른 12단계 계획
    steps = [step("inspect_scene", location_id=f"L{n}") for n in range(1, 7)]
    steps += [step("verify_alibi", suspect_id=f"S{n}") for n in range(1, 4)]
    steps += [
        step("interview_suspect", suspect_id="S1", topic_id=f"T{n}")
        for n in range(1, 4)
    ]
    state, model = run_fixed([make_plan(steps)])
    # 10단계만 처리·기록
    assert len(state["investigation_history"]) == 10
    assert len(tool_messages(state)) == 10
    assert state["tool_call_count"] == 10
    assert state["stop_reason"] == "budget_exhausted"
    # 보고서 작성됨
    assert model.report_call_count == 1
    assert state["final_report"] is not None


# source_steps 오류 테스트
# 이후 단계·없는 번호·빈 목록을 가리키면 인자 오류이고 예산이 차감되는지 확인하는 함수
def test_source_steps_errors() -> None:
    # 1단계 현장 조사, 2~4단계 잘못된 교차 검증
    plan = make_plan(
        [
            step("inspect_scene", location_id="L1"),
            step("cross_check_evidence", source_steps=[3]),
            step("cross_check_evidence", source_steps=[99]),
            step("cross_check_evidence", source_steps=[]),
        ]
    )
    state, _ = run_fixed([plan])
    messages = [str(item.content) for item in tool_messages(state)]
    # 각 오류 메시지 확인
    assert messages[1].startswith(
        "도구 인자 오류: source_steps가 앞선 단계를 가리키지 않습니다: 3"
    )
    assert messages[2].startswith(
        "도구 인자 오류: source_steps가 앞선 단계를 가리키지 않습니다: 99"
    )
    assert messages[3].startswith("도구 인자 오류: source_steps가 비어 있습니다.")
    # 4단계 모두 예산 차감
    assert state["tool_call_count"] == 4
    assert all(entry["error"] for entry in state["investigation_history"][1:])


# 교차 검증 증거 수 오류 테스트
# source_steps 단계 증거가 1개뿐이면 도구 검증 오류이고 예산이 차감되는지 확인하는 함수
def test_cross_check_with_one_evidence() -> None:
    # 1단계(E1) 증거 하나로 교차 검증
    plan = make_plan(
        [
            step("inspect_scene", location_id="L1"),
            step("cross_check_evidence", source_steps=[1]),
        ]
    )
    state, _ = run_fixed([plan])
    message = str(tool_messages(state)[1].content)
    # 도구의 개수 검증 오류
    assert message.startswith("도구 인자 오류: 교차 검증할 증거는 2~5개여야 합니다")
    assert state["tool_call_count"] == 2
    assert state["investigation_history"][1]["args"]["evidence_ids"] == ["E1"]


# 필수 인자 누락 테스트
# 현장 조사 단계에 장소가 없으면 입력 검증 오류이고 예산이 차감되는지 확인하는 함수
def test_missing_required_argument() -> None:
    # 장소 없는 현장 조사
    state, _ = run_fixed([make_plan([step("inspect_scene")])])
    message = str(tool_messages(state)[0].content)
    # 입력 검증 오류와 차감 확인
    assert message.startswith("도구 인자 오류:")
    assert "location_id" in message
    assert state["tool_call_count"] == 1


# 중복 단계 테스트
# 같은 단계가 두 번 있으면 두 번째가 중복으로 처리되는지 확인하는 함수
def test_duplicate_step() -> None:
    # 같은 현장 조사 2단계
    plan = make_plan(
        [
            step("inspect_scene", location_id="L1"),
            step("inspect_scene", location_id="L1"),
        ]
    )
    state, _ = run_fixed([plan])
    # 두 번째는 중복
    assert str(tool_messages(state)[1].content).startswith("중복 조사: 1번째 호출")
    assert state["investigation_history"][1]["error"] == "duplicate"
    assert state["tool_call_count"] == 2


# 계획 형식 오류 1회 테스트
# 계획이 한 번 형식 오류여도 다시 요청해 정상 진행하는지 확인하는 함수
def test_plan_parse_error_once_then_ok() -> None:
    # 형식 오류 1회 후 정상 계획
    state, model = run_fixed([MALFORMED_PLAN, solution_plan()])
    # 두 번 요청 후 진행
    assert model.plan_call_count == 2
    assert len(state["investigation_history"]) == 5
    assert state["status"] != "failed"


# 계획 형식 오류 2회 테스트
# 계획이 두 번 연속 형식 오류면 계획 실패로 끝나는지 확인하는 함수
def test_plan_parse_error_twice_fails() -> None:
    # 형식 오류 2회
    state, model = run_fixed([MALFORMED_PLAN, MALFORMED_PLAN])
    # 계획 실패, 조사·보고서 없음
    assert state["status"] == "failed"
    assert state["stop_reason"] == "plan_error"
    assert state["error"] is not None
    assert state["tool_call_count"] == 0
    assert model.report_call_count == 0


# 같은 초기 정보 테스트
# 계획 수립에 쓰인 브리핑이 적응형 첫 메시지의 브리핑과 같은지 확인하는 함수
def test_same_brief_as_adaptive() -> None:
    # 고정 계획형 실행 후 계획 요청 메시지
    _, fixed_model = run_fixed([solution_plan()])
    planner_human = fixed_model.plan_received[0][1]
    assert isinstance(planner_human, HumanMessage)
    fixed_brief = str(planner_human.content).removesuffix("\n" + build_plan_request())
    # 적응형 실행 후 첫 HumanMessage
    adaptive_model = ScriptedChatModel(
        responses=[finish_message()], reports=[withhold_report()]
    )
    run_investigation(CASE_ID, adaptive_model)
    adaptive_human = adaptive_model.received[0][1]
    adaptive_brief = str(adaptive_human.content).removesuffix("\n수사를 시작하라.")
    # 브리핑이 같아야 함
    assert fixed_brief == adaptive_brief
    assert fixed_brief != str(planner_human.content)


# 같은 도구 테스트
# 계획 단계에서 고를 수 있는 도구가 적응형 도구 명세 이름과 같은지 확인하는 함수
def test_same_tools_as_adaptive() -> None:
    # 계획 단계 도구 허용 값
    allowed = set(get_args(PlannedStep.model_fields["tool"].annotation))
    # 적응형 도구 이름
    adaptive = {tool["function"]["name"] for tool in get_llm_tools()}
    assert allowed == adaptive
