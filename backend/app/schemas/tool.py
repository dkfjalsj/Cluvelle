from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.case import EvidenceSourceTool, ToolName

# 교차 검증 관계 종류
RelationType = Literal[
    "same_person_overlap_different_place",
    "same_person_overlap_same_place",
    "same_person_no_overlap",
    "different_people_same_place_overlap",
    "unidentified_time_overlap",
]


# 증거 보기
# 도구 결과로 돌려줄 증거의 ID·출처·요약만 담는 클래스 (사실 관계는 제외)
class EvidenceView(BaseModel):
    # 알 수 없는 필드가 들어오면 검증 실패
    model_config = ConfigDict(extra="forbid")

    # 증거 ID
    id: str
    # 증거를 내놓은 조사 도구
    source_tool: EvidenceSourceTool
    # 증거 요약 문장
    summary: str


# 조회 도구 결과
# 조회 도구 호출의 인자·발견 여부·확보 증거·안내 문구를 담는 클래스
class InvestigationResult(BaseModel):
    # 알 수 없는 필드가 들어오면 검증 실패
    model_config = ConfigDict(extra="forbid")

    # 호출한 도구 이름
    tool: ToolName
    # 받은 인자 (키 이름 그대로)
    args: dict[str, str]
    # 증거 발견 여부
    found: bool
    # 확보한 증거 목록
    evidence: list[EvidenceView]
    # 안내 문구
    message: str


# 사실 관계
# 교차 검증으로 계산한 두 증거 사이의 사실 관계 하나를 담는 클래스
class FactRelation(BaseModel):
    # 알 수 없는 필드가 들어오면 검증 실패
    model_config = ConfigDict(extra="forbid")

    # 관계 종류
    type: RelationType
    # 관계에 쓰인 증거 ID 2개
    evidence_ids: list[str]
    # 관계에 등장한 확인된 인물 ID
    person_ids: list[str]
    # 사실만 적은 설명 문장
    detail: str


# 교차 검증 결과
# 교차 검증 대상 증거와 계산된 사실 관계 목록, 안내 문구를 담는 클래스
class CrossCheckResult(BaseModel):
    # 알 수 없는 필드가 들어오면 검증 실패
    model_config = ConfigDict(extra="forbid")

    # 도구 이름
    tool: Literal["cross_check_evidence"]
    # 교차 검증한 증거 ID (입력 순서)
    evidence_ids: list[str]
    # 사실 관계 목록
    relations: list[FactRelation]
    # 안내 문구
    message: str
