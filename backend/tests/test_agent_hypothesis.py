import pytest
from agent_fakes import (
    ScriptedChatModel,
    finish_message,
    tool_call_message,
    withhold_report,
)
from langchain_core.messages import ToolMessage
from pydantic import ValidationError

from app.agent.runner import run_investigation
from app.agent.tool_specs import (
    ADAPTIVE_TOOL_INPUT_MODELS,
    TOOL_INPUT_MODELS,
    get_llm_tools,
)

# 검증 대상 사건 ID
CASE_ID = "CASE-001"


# 가설 필수 검증 테스트
# 적응형 입력 모델이 가설 누락·공백·200자 초과를 거부하고 앞뒤 공백을 정리하는지 확인하는 함수
def test_hypothesis_validation() -> None:
    # 적응형 현장 조사 입력 모델
    model = ADAPTIVE_TOOL_INPUT_MODELS["inspect_scene"]
    base = {"location_id": "L1", "reason": "현장 확인"}
    # 누락·공백·200자 초과 거부
    for bad in ({}, {"hypothesis": "   "}, {"hypothesis": "가" * 201}):
        with pytest.raises(ValidationError):
            model.model_validate({**base, **bad})
    # 정상 값은 앞뒤 공백 제거
    validated = model.model_validate(
        {**base, "hypothesis": "  보관함은 열쇠로 열렸다  "}
    )
    assert validated.hypothesis == "보관함은 열쇠로 열렸다"
    # 200자 정확히는 허용
    model.model_validate({**base, "hypothesis": "가" * 200})


# 고정 계획형 입력 유지 테스트
# 고정 계획형 입력 모델에는 가설 필드가 없고, LLM 도구 명세에는 가설이 필수인지 확인하는 함수
def test_fixed_models_unchanged_and_llm_tools_require_hypothesis() -> None:
    # 고정 계획형 모델에는 가설 없음
    for model in TOOL_INPUT_MODELS.values():
        assert "hypothesis" not in model.model_fields
    # LLM 도구 명세에는 가설 필수
    for tool in get_llm_tools():
        assert "hypothesis" in tool["function"]["parameters"]["required"]


# 가설 기록 테스트
# 가설이 조사 기록에 남고 도구 인자(args)에서는 빠지는지 확인하는 함수
def test_hypothesis_recorded_not_in_args() -> None:
    # 가설을 담은 현장 조사 후 수사 종료
    model = ScriptedChatModel(
        responses=[
            tool_call_message(
                "inspect_scene",
                {
                    "location_id": "L1",
                    "reason": "현장 확인",
                    "hypothesis": " 내부자 소행 ",
                },
                "c1",
            ),
            finish_message(),
        ],
        reports=[withhold_report()],
    )
    state = run_investigation(CASE_ID, model)
    entry = state["investigation_history"][0]
    # 정리된 가설이 기록되고 인자에는 없음
    assert entry["hypothesis"] == "내부자 소행"
    assert entry["args"] == {"location_id": "L1"}
    assert entry["error"] is None


# 가설 공백 오류 테스트
# 가설이 공백뿐이면 입력 검증 오류가 되고 예산이 차감되는지 확인하는 함수
def test_blank_hypothesis_is_argument_error() -> None:
    # 공백 가설 호출
    model = ScriptedChatModel(
        responses=[
            tool_call_message(
                "inspect_scene",
                {"location_id": "L1", "reason": "현장 확인", "hypothesis": "   "},
                "c1",
            ),
            finish_message(),
        ],
        reports=[withhold_report()],
    )
    state = run_investigation(CASE_ID, model)
    entry = state["investigation_history"][0]
    message = next(m for m in state["messages"] if isinstance(m, ToolMessage))
    # 인자 오류이고 가설 관련 원인
    assert str(message.content).startswith("도구 인자 오류:")
    assert "hypothesis" in str(message.content)
    assert state["tool_call_count"] == 1
    assert entry["error"] is not None


# 가설만 다른 같은 조사 중복 테스트
# 가설만 바꾼 같은 조사가 중복으로 판정되는지 확인하는 함수
def test_duplicate_ignores_hypothesis() -> None:
    # 같은 현장 조사, 가설만 다름
    model = ScriptedChatModel(
        responses=[
            tool_call_message(
                "inspect_scene",
                {"location_id": "L1", "reason": "확인", "hypothesis": "가설 A"},
                "a",
            ),
            tool_call_message(
                "inspect_scene",
                {"location_id": "L1", "reason": "재확인", "hypothesis": "가설 B"},
                "b",
            ),
            finish_message(),
        ],
        reports=[withhold_report()],
    )
    state = run_investigation(CASE_ID, model)
    second = state["investigation_history"][1]
    # 두 번째는 중복
    assert second["error"] == "duplicate"
    assert second["hypothesis"] == "가설 B"
