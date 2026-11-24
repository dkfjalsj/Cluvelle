import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# 난이도 값
Difficulty = Literal["intro", "normal", "challenge"]

# 조사 도구 이름 (교차 검증 포함 5개)
ToolName = Literal[
    "inspect_scene",
    "interview_suspect",
    "check_cctv",
    "verify_alibi",
    "cross_check_evidence",
]

# 증거를 직접 내놓는 조사 도구 이름 (교차 검증 제외 4개)
EvidenceSourceTool = Literal[
    "inspect_scene",
    "interview_suspect",
    "check_cctv",
    "verify_alibi",
]

# 사건 ID 형식 (예: CASE-001)
CASE_ID_PATTERN = r"^CASE-\d{3}$"
# 종류별 ID 형식
SUSPECT_ID_PATTERN = r"^S\d+$"
LOCATION_ID_PATTERN = r"^L\d+$"
CAMERA_ID_PATTERN = r"^C\d+$"
TOPIC_ID_PATTERN = r"^T\d+$"
EVIDENCE_ID_PATTERN = r"^E\d+$"
# 시각 형식 (00:00~23:59)
TIME_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"
# 시간대 형식 (HH:MM-HH:MM)
TIME_WINDOW_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d-([01]\d|2[0-3]):[0-5]\d$"

# 사건 밖 장소를 나타내는 place 값
OFF_SITE_PLACE = "off_site"

# 조사 도구별로 증거 locator에 반드시 있어야 하는 필드 (이 외 필드는 없어야 함)
LOCATOR_FIELDS_BY_TOOL: dict[str, frozenset[str]] = {
    "inspect_scene": frozenset({"location_id"}),
    "interview_suspect": frozenset({"suspect_id", "topic_id"}),
    "check_cctv": frozenset({"camera_id", "time_window"}),
    "verify_alibi": frozenset({"suspect_id"}),
}


# 엄격 모델 기반
# 정의되지 않은 필드를 거부하도록 설정한 공통 기반 클래스
class StrictModel(BaseModel):
    # 알 수 없는 필드가 들어오면 검증 실패
    model_config = ConfigDict(extra="forbid")


# 용의자
# 사건 용의자의 ID·이름·역할·소개를 담는 클래스
class Suspect(StrictModel):
    # 용의자 ID (S숫자)
    id: str = Field(pattern=SUSPECT_ID_PATTERN)
    # 이름
    name: str
    # 사건 속 역할
    role: str
    # 소개 문장
    description: str


# 장소
# 조사 가능한 장소의 ID와 이름을 담는 클래스
class Location(StrictModel):
    # 장소 ID (L숫자)
    id: str = Field(pattern=LOCATION_ID_PATTERN)
    # 장소 이름
    name: str


# 카메라
# CCTV 카메라의 위치와 조회 가능한 시간대를 담는 클래스
class Camera(StrictModel):
    # 카메라 ID (C숫자)
    id: str = Field(pattern=CAMERA_ID_PATTERN)
    # 카메라 이름
    name: str
    # 카메라가 설치된 장소 ID
    location_id: str = Field(pattern=LOCATION_ID_PATTERN)
    # 조회 가능한 시간대 목록 (HH:MM-HH:MM)
    time_windows: list[str]

    # 시간대 목록 검증
    # 각 시간대의 형식과 시작<끝 순서, 목록 내 중복 여부를 확인하는 함수
    @field_validator("time_windows")
    @classmethod
    def validate_time_windows(cls, value: list[str]) -> list[str]:
        # 시간대마다 형식과 순서 확인
        for window in value:
            # HH:MM-HH:MM 형식이 아니면 오류
            if not _matches(TIME_WINDOW_PATTERN, window):
                raise ValueError(f"시간대 형식이 올바르지 않습니다: {window}")
            # 시작과 끝으로 나누기
            start, end = window.split("-")
            # 시작이 끝보다 앞서야 함 (0자리 채움 형식이라 문자열 비교로 충분)
            if not start < end:
                raise ValueError(f"시간대의 시작이 끝보다 앞서야 합니다: {window}")
        # 같은 시간대가 두 번 이상 있으면 오류
        if len(set(value)) != len(value):
            raise ValueError("카메라 시간대가 중복되었습니다.")
        # 검증된 목록 반환
        return value


# 질문 주제
# 심문에서 고를 수 있는 질문 주제의 ID와 이름을 담는 클래스
class Topic(StrictModel):
    # 주제 ID (T숫자)
    id: str = Field(pattern=TOPIC_ID_PATTERN)
    # 주제 이름
    name: str


# 사실 관계
# 증거가 담은 진술·기록의 인물·장소·시간 구간을 담는 클래스
class Fact(StrictModel):
    # 종류 (claim: 진술, record: 기록)
    kind: Literal["claim", "record"]
    # 관련 인물 ID (용의자 ID 또는 null)
    person_id: str | None
    # 장소 ID 또는 "off_site"
    place: str
    # 시작 시각 (HH:MM)
    start: str = Field(pattern=TIME_PATTERN)
    # 끝 시각 (HH:MM)
    end: str = Field(pattern=TIME_PATTERN)

    # 시간 순서 검증
    # 시작 시각이 끝 시각보다 늦지 않은지 확인하는 함수
    @model_validator(mode="after")
    def validate_time_order(self) -> "Fact":
        # 시작이 끝보다 늦으면 오류
        if self.start > self.end:
            raise ValueError(
                f"사실의 시작({self.start})이 끝({self.end})보다 늦습니다."
            )
        # 검증된 객체 반환
        return self


# 증거 조회 위치
# 증거가 어느 도구 인자 조합에서 조회되는지 지정하는 클래스
class EvidenceLocator(StrictModel):
    # 장소 ID (inspect_scene)
    location_id: str | None = None
    # 용의자 ID (interview_suspect, verify_alibi)
    suspect_id: str | None = None
    # 주제 ID (interview_suspect)
    topic_id: str | None = None
    # 카메라 ID (check_cctv)
    camera_id: str | None = None
    # 시간대 (check_cctv)
    time_window: str | None = None


# 증거
# 조사 도구로 얻을 수 있는 증거의 출처·위치·요약·사실 관계를 담는 클래스
class Evidence(StrictModel):
    # 증거 ID (E숫자)
    id: str = Field(pattern=EVIDENCE_ID_PATTERN)
    # 증거를 내놓는 조사 도구
    source_tool: EvidenceSourceTool
    # 조회 위치
    locator: EvidenceLocator
    # 증거 요약 문장
    summary: str
    # 사실 관계 목록 (빈 목록 허용)
    facts: list[Fact]


# 사건 파일
# 공개 정보와 도구 조회용 증거를 모두 담은 사건 데이터 클래스
class CaseFile(StrictModel):
    # 사건 ID (CASE-###)
    case_id: str = Field(pattern=CASE_ID_PATTERN)
    # 사건 데이터 버전
    version: int
    # 사건 제목
    title: str
    # 난이도
    difficulty: Difficulty
    # 한 줄 소개
    summary: str
    # 사건 도입부
    introduction: str
    # 조사 예산 (1~10, 기본 10)
    tool_budget: int = Field(default=10, ge=1, le=10)
    # 용의자 목록
    suspects: list[Suspect]
    # 장소 목록
    locations: list[Location]
    # 카메라 목록
    cameras: list[Camera]
    # 질문 주제 목록
    topics: list[Topic]
    # 증거 목록 (도구로만 조회)
    evidence: list[Evidence]

    # 사건 전체 정합성 검증
    # ID 중복, 카메라 장소, 증거 locator, 사실 관계 참조가 올바른지 확인하는 함수
    @model_validator(mode="after")
    def validate_references(self) -> "CaseFile":
        # 종류별 ID 중복 검사
        _ensure_unique("용의자", [suspect.id for suspect in self.suspects])
        _ensure_unique("장소", [location.id for location in self.locations])
        _ensure_unique("카메라", [camera.id for camera in self.cameras])
        _ensure_unique("주제", [topic.id for topic in self.topics])
        _ensure_unique("증거", [item.id for item in self.evidence])

        # 참조 검사용 ID 집합과 카메라 조회 표
        suspect_ids = {suspect.id for suspect in self.suspects}
        location_ids = {location.id for location in self.locations}
        topic_ids = {topic.id for topic in self.topics}
        cameras_by_id = {camera.id: camera for camera in self.cameras}

        # 카메라 설치 장소가 장소 목록에 있는지 확인
        for camera in self.cameras:
            if camera.location_id not in location_ids:
                raise ValueError(
                    f"카메라 {camera.id}의 장소 {camera.location_id}가 없습니다."
                )

        # 증거마다 locator와 사실 관계 확인
        for item in self.evidence:
            # locator에 값이 채워진 필드 집합
            filled = set(item.locator.model_dump(exclude_none=True))
            # 도구에 필요한 필드 집합
            required = LOCATOR_FIELDS_BY_TOOL[item.source_tool]
            # 필요한 필드만 정확히 있어야 함
            if filled != required:
                raise ValueError(
                    f"증거 {item.id}의 locator 필드 {sorted(filled)}가 "
                    f"{item.source_tool}에 필요한 {sorted(required)}와 다릅니다."
                )
            # locator가 가리키는 ID가 실제로 있는지 확인
            locator = item.locator
            if (
                locator.location_id is not None
                and locator.location_id not in location_ids
            ):
                raise ValueError(
                    f"증거 {item.id}가 없는 장소 {locator.location_id}를 가리킵니다."
                )
            if locator.suspect_id is not None and locator.suspect_id not in suspect_ids:
                raise ValueError(
                    f"증거 {item.id}가 없는 용의자 {locator.suspect_id}를 가리킵니다."
                )
            if locator.topic_id is not None and locator.topic_id not in topic_ids:
                raise ValueError(
                    f"증거 {item.id}가 없는 주제 {locator.topic_id}를 가리킵니다."
                )
            if locator.camera_id is not None:
                # 카메라가 없으면 오류
                camera = cameras_by_id.get(locator.camera_id)
                if camera is None:
                    raise ValueError(
                        f"증거 {item.id}가 없는 카메라 {locator.camera_id}를 가리킵니다."
                    )
                # 시간대가 그 카메라의 조회 가능 시간대 안에 있어야 함
                if locator.time_window not in camera.time_windows:
                    raise ValueError(
                        f"증거 {item.id}의 시간대 {locator.time_window}가 "
                        f"카메라 {camera.id}의 시간대에 없습니다."
                    )
            # 사실 관계의 인물·장소 참조 확인
            for fact in item.facts:
                # 인물은 용의자 ID 또는 null
                if fact.person_id is not None and fact.person_id not in suspect_ids:
                    raise ValueError(
                        f"증거 {item.id}의 사실이 없는 인물 {fact.person_id}를 가리킵니다."
                    )
                # 장소는 장소 ID 또는 off_site
                if fact.place != OFF_SITE_PLACE and fact.place not in location_ids:
                    raise ValueError(
                        f"증거 {item.id}의 사실이 없는 장소 {fact.place}를 가리킵니다."
                    )

        # 검증된 객체 반환
        return self


# 공개 사건 정보
# 사건 파일에서 증거를 뺀, 수사 시작 전에 공개해도 되는 정보 클래스
class PublicCase(StrictModel):
    # 사건 ID
    case_id: str
    # 사건 데이터 버전
    version: int
    # 사건 제목
    title: str
    # 난이도
    difficulty: Difficulty
    # 한 줄 소개
    summary: str
    # 사건 도입부
    introduction: str
    # 조사 예산
    tool_budget: int
    # 용의자 목록
    suspects: list[Suspect]
    # 장소 목록
    locations: list[Location]
    # 카메라 목록 (조회 가능 시간대 포함)
    cameras: list[Camera]
    # 질문 주제 목록
    topics: list[Topic]


# 사건 요약
# 사건 목록 화면에 보여줄 ID·제목·난이도·한 줄 소개를 담는 클래스
class CaseSummary(StrictModel):
    # 사건 ID
    case_id: str
    # 사건 제목
    title: str
    # 난이도
    difficulty: Difficulty
    # 한 줄 소개
    summary: str


# 정규식 일치 확인
# 문자열이 주어진 정규식 전체와 일치하는지 반환하는 함수
def _matches(pattern: str, value: str) -> bool:
    # 전체 일치 여부 반환
    return re.fullmatch(pattern, value) is not None


# ID 중복 검사
# 목록에 같은 ID가 두 번 이상 있으면 종류 이름과 함께 오류를 내는 함수
def _ensure_unique(kind: str, ids: list[str]) -> None:
    # 이미 본 ID 집합
    seen: set[str] = set()
    # 순서대로 보며 중복 확인
    for item_id in ids:
        # 이미 본 ID면 오류
        if item_id in seen:
            raise ValueError(f"{kind} ID {item_id}가 중복되었습니다.")
        # 본 ID로 기록
        seen.add(item_id)
