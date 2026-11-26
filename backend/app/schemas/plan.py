from pydantic import BaseModel, Field

from app.schemas.case import ToolName


# 계획 단계
# 고정 계획형 조사 계획의 한 단계(도구와 인자, 계획 이유)를 평평한 구조로 담는 클래스
class PlannedStep(BaseModel):
    # 사용할 조사 도구
    tool: ToolName = Field(description="사용할 조사 도구 이름")
    # 장소 ID (inspect_scene)
    location_id: str | None = Field(default=None, description="장소 ID (inspect_scene)")
    # 용의자 ID (interview_suspect, verify_alibi)
    suspect_id: str | None = Field(
        default=None, description="용의자 ID (interview_suspect, verify_alibi)"
    )
    # 질문 주제 ID (interview_suspect)
    topic_id: str | None = Field(
        default=None, description="질문 주제 ID (interview_suspect)"
    )
    # 카메라 ID (check_cctv)
    camera_id: str | None = Field(default=None, description="카메라 ID (check_cctv)")
    # 시간대 (check_cctv)
    time_window: str | None = Field(default=None, description="시간대 (check_cctv)")
    # 교차 검증할 증거를 가져올 앞선 계획 단계 번호 (cross_check_evidence 전용, 1부터)
    source_steps: list[int] | None = Field(
        default=None,
        description="cross_check_evidence 전용: 증거를 가져올 앞선 단계 번호 목록(1부터)",
    )
    # 이 단계를 계획한 이유
    reason: str = Field(description="이 단계를 계획한 이유 한 문장")


# 조사 계획
# 고정 계획형이 시작 시 한 번에 세우는 조사 단계 목록과 전체 의도를 담는 클래스
class InvestigationPlan(BaseModel):
    # 조사 단계 목록 (1개 이상)
    steps: list[PlannedStep] = Field(
        min_length=1, description="순서대로 실행할 조사 단계"
    )
    # 계획 전체 의도
    rationale: str = Field(description="계획 전체 의도 2~3문장")
