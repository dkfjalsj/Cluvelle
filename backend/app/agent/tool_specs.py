from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# reason 필드 설명
REASON_DESCRIPTION = "이 도구를 지금 선택한 이유를 한 문장으로"
# reason 최대 길이
REASON_MAX_LENGTH = 200


# 도구 입력 기반
# 정의되지 않은 필드를 거부하고 reason을 필수로 받는 도구 입력 공통 클래스
class ToolInputBase(BaseModel):
    # 알 수 없는 필드가 들어오면 검증 실패
    model_config = ConfigDict(extra="forbid")

    # 도구 선택 이유 (앞뒤 공백 제거 후 1~200자)
    reason: str = Field(description=REASON_DESCRIPTION)

    # 선택 이유 검증
    # 앞뒤 공백을 제거한 뒤 비어 있거나 200자를 넘으면 오류를 내는 함수
    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        # 앞뒤 공백 제거
        stripped = value.strip()
        # 비어 있으면 오류
        if not stripped:
            raise ValueError("reason은 비어 있을 수 없습니다.")
        # 너무 길면 오류
        if len(stripped) > REASON_MAX_LENGTH:
            raise ValueError(f"reason은 {REASON_MAX_LENGTH}자 이하여야 합니다.")
        # 정리된 값 반환
        return stripped


# 현장 조사 입력
# inspect_scene 도구의 입력 인자를 정의하는 클래스
class InspectSceneInput(ToolInputBase):
    # 조사할 장소 ID
    location_id: str = Field(description="조사할 장소 ID (예: L1)")


# 용의자 심문 입력
# interview_suspect 도구의 입력 인자를 정의하는 클래스
class InterviewSuspectInput(ToolInputBase):
    # 심문할 용의자 ID
    suspect_id: str = Field(description="심문할 용의자 ID (예: S1)")
    # 질문 주제 ID
    topic_id: str = Field(description="질문할 주제 ID (예: T1)")


# CCTV 확인 입력
# check_cctv 도구의 입력 인자를 정의하는 클래스
class CheckCctvInput(ToolInputBase):
    # 확인할 카메라 ID
    camera_id: str = Field(description="확인할 카메라 ID (예: C1)")
    # 확인할 시간대
    time_window: str = Field(description="확인할 시간대 (예: 20:00-21:00)")


# 알리바이 확인 입력
# verify_alibi 도구의 입력 인자를 정의하는 클래스
class VerifyAlibiInput(ToolInputBase):
    # 출입 기록을 조회할 용의자 ID
    suspect_id: str = Field(description="출입 기록을 조회할 용의자 ID (예: S1)")


# 교차 검증 입력
# cross_check_evidence 도구의 입력 인자를 정의하는 클래스
class CrossCheckInput(ToolInputBase):
    # 비교할 증거 ID 목록
    evidence_ids: list[str] = Field(description="비교할 확보 증거 ID 목록 (2~5개)")


# 도구 이름 → 입력 모델
TOOL_INPUT_MODELS: dict[str, type[BaseModel]] = {
    "inspect_scene": InspectSceneInput,
    "interview_suspect": InterviewSuspectInput,
    "check_cctv": CheckCctvInput,
    "verify_alibi": VerifyAlibiInput,
    "cross_check_evidence": CrossCheckInput,
}

# 도구 이름 → 설명
TOOL_DESCRIPTIONS: dict[str, str] = {
    "inspect_scene": "공개된 장소 하나를 조사해 현장 증거를 확인한다.",
    "interview_suspect": "용의자 한 명에게 공개된 질문 주제 하나로 진술을 듣는다.",
    "check_cctv": "카메라 하나의 공개된 시간대 하나의 영상 요약을 확인한다.",
    "verify_alibi": "용의자 한 명의 출입 기록을 조회한다.",
    "cross_check_evidence": "이미 확보한 증거 2~5개의 시간·장소 사실 관계를 비교한다. 판단은 하지 않는다.",
}


# LLM 도구 목록 생성
# 5개 도구를 bind_tools에 넘길 수 있는 함수 호출 형식으로 만들어 반환하는 함수
def get_llm_tools() -> list[dict[str, Any]]:
    # 도구 정의 목록
    tools: list[dict[str, Any]] = []
    # 도구마다 이름·설명·입력 스키마 조합 (사건 객체는 스키마에 넣지 않음)
    for name, model in TOOL_INPUT_MODELS.items():
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": TOOL_DESCRIPTIONS[name],
                    "parameters": model.model_json_schema(),
                },
            }
        )
    # 도구 정의 목록 반환
    return tools
