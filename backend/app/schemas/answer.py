import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.case import (
    CASE_ID_PATTERN,
    EVIDENCE_ID_PATTERN,
    SUSPECT_ID_PATTERN,
    ToolName,
)


# 해결 경로 단계
# 설계상 최단 해결 경로의 한 단계(도구와 인자)를 담는 클래스
class SolutionStep(BaseModel):
    # 알 수 없는 필드가 들어오면 검증 실패
    model_config = ConfigDict(extra="forbid")

    # 호출할 조사 도구
    tool: ToolName
    # 도구 인자 (문자열 또는 문자열 목록)
    args: dict[str, str | list[str]]


# 정답 키
# 사건의 범인·결정적 증거·오해 유발 증거·해결 경로·채점 메모를 담는 클래스
class AnswerKey(BaseModel):
    # 알 수 없는 필드가 들어오면 검증 실패
    model_config = ConfigDict(extra="forbid")

    # 사건 ID
    case_id: str = Field(pattern=CASE_ID_PATTERN)
    # 범인 용의자 ID
    culprit_id: str = Field(pattern=SUSPECT_ID_PATTERN)
    # 결정적 증거 ID 목록 (2~3개)
    decisive_evidence_ids: list[str] = Field(min_length=2, max_length=3)
    # 오해를 유발하는 증거 ID 목록
    misleading_evidence_ids: list[str]
    # 설계상 최단 해결 경로 (1~10단계)
    solution_path: list[SolutionStep] = Field(min_length=1, max_length=10)
    # 채점 메모
    grading_notes: str

    # 증거 ID 목록 검증
    # 각 증거 ID의 형식과 목록 안 중복 여부를 확인하는 함수
    @field_validator("decisive_evidence_ids", "misleading_evidence_ids")
    @classmethod
    def validate_evidence_ids(cls, value: list[str]) -> list[str]:
        # 이미 본 ID 집합
        seen: set[str] = set()
        # ID마다 형식과 중복 확인
        for evidence_id in value:
            # 형식이 E숫자가 아니면 오류
            if not _is_evidence_id(evidence_id):
                raise ValueError(f"증거 ID 형식이 올바르지 않습니다: {evidence_id}")
            # 이미 본 ID면 오류
            if evidence_id in seen:
                raise ValueError(f"증거 ID {evidence_id}가 중복되었습니다.")
            # 본 ID로 기록
            seen.add(evidence_id)
        # 검증된 목록 반환
        return value


# 증거 ID 형식 확인
# 문자열이 E숫자 형식의 증거 ID인지 반환하는 함수
def _is_evidence_id(value: str) -> bool:
    # 전체 일치 여부 반환
    return re.fullmatch(EVIDENCE_ID_PATTERN, value) is not None
