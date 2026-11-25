import re

import pytest

from app.schemas.answer import AnswerKey
from app.schemas.case import CaseFile
from app.services.answer_key import load_answer_key, validate_answer_against_case
from app.services.case_repository import CaseRepository
from app.services.case_validation import validate_case
from app.tools import check_cctv, cross_check_evidence

# 검증 대상 사건 ID
CASE_ID = "CASE-002"
# 설명이 있어야 하는 장소·카메라와 그 값
LOCATION_DESCRIPTIONS = {
    "L1": "분실 진열장 있음",
    "L2": "2전시실 정문과 학예실 문이 있음",
    "L3": "직원 전용",
    "L5": "리셉션 장소",
    "L7": "2층",
}
CAMERA_DESCRIPTIONS = {
    "C2": "2전시실 정문과 학예실 문이 보임",
    "C3": "직원 통로 입구 바로 위 근접 설치",
}


# 사건 픽스처
# 기본 경로에서 CASE-002 사건을 로드해 반환하는 함수
@pytest.fixture
def case() -> CaseFile:
    # 기본 사건 폴더에서 로드
    return CaseRepository().load_case(CASE_ID)


# 정답 픽스처
# 기본 경로에서 CASE-002 정답을 로드해 반환하는 함수
@pytest.fixture
def answer() -> AnswerKey:
    # 기본 정답 폴더에서 로드
    return load_answer_key(CASE_ID)


# 로드 및 정답 대조 테스트
# CASE-002 사건·정답이 로드되고 대조 검증을 통과하는지 확인하는 함수
def test_case_and_answer_load(case: CaseFile, answer: AnswerKey) -> None:
    # 기본 정보 확인
    assert case.case_id == CASE_ID
    assert answer.culprit_id == "S2"
    # 대조 검증이 예외 없이 통과해야 함
    validate_answer_against_case(answer, case)


# 구성 개수 테스트
# 용의자·장소·카메라·시간대·주제·증거 개수가 설계와 같은지 확인하는 함수
def test_case_counts(case: CaseFile) -> None:
    # 종류별 개수 확인
    assert len(case.suspects) == 3
    assert len(case.locations) == 7
    assert len(case.cameras) == 3
    assert all(len(camera.time_windows) == 3 for camera in case.cameras)
    assert len(case.topics) == 4
    assert len(case.evidence) == 23


# 설명 필드 테스트
# 설명이 표에 있는 장소·카메라에만 있고 값이 같으며 나머지에는 없는지 확인하는 함수
def test_descriptions(case: CaseFile) -> None:
    # 장소 설명 확인 (없어야 하는 장소는 None)
    for location in case.locations:
        assert location.description == LOCATION_DESCRIPTIONS.get(location.id)
    # 카메라 설명 확인 (없어야 하는 카메라는 None)
    for camera in case.cameras:
        assert camera.description == CAMERA_DESCRIPTIONS.get(camera.id)
    # 설명 없는 항목 명시 확인
    locations = {location.id: location for location in case.locations}
    cameras = {camera.id: camera for camera in case.cameras}
    assert locations["L4"].description is None
    assert locations["L6"].description is None
    assert cameras["C1"].description is None


# 사건 밖 표기 테스트
# off_site_label이 "미술관 밖"인지 확인하는 함수
def test_off_site_label(case: CaseFile) -> None:
    # 표기 확인
    assert case.off_site_label == "미술관 밖"


# 사건 검증 테스트
# 사건 검증 규칙을 모두 통과하고 통계가 설계값과 같은지 확인하는 함수
def test_validate_case(case: CaseFile, answer: AnswerKey) -> None:
    # 검증 실행
    report = validate_case(case, answer)
    assert report.passed, report.errors
    stats = report.stats
    assert stats is not None
    # 설계값 확인
    assert stats.combo_count == 31
    assert stats.combos_with_evidence == 22
    assert stats.combos_without_evidence == 9
    assert stats.decisive_count == 3
    assert stats.misleading_count == 2
    assert stats.path_length == 5


# 한 위치 여러 증거 테스트
# 하역장 카메라 20:00-21:00 조회가 E19, E20을 순서대로 반환하는지 확인하는 함수
def test_cctv_returns_two_evidence(case: CaseFile) -> None:
    # 하역장 카메라 조회
    result = check_cctv(case, "C3", "20:00-21:00")
    # 증거 ID 순서 확인
    assert [item.id for item in result.evidence] == ["E19", "E20"]


# 교차 검증 기대값 테스트
# 증거 조합마다 관계 종류·건수·인물이 설계와 정확히 같은지 확인하는 함수
@pytest.mark.parametrize(
    ("evidence_ids", "expected_type", "expected_count", "person"),
    [
        (["E7", "E20"], "same_person_overlap_different_place", 2, "S2"),
        (["E7", "E22"], "same_person_overlap_same_place", 1, "S2"),
        (["E7", "E23"], "same_person_overlap_different_place", 1, "S2"),
        (["E9", "E21"], "same_person_overlap_different_place", 1, "S1"),
        (["E9", "E17"], None, 0, None),
        (["E10", "E19"], "same_person_overlap_same_place", 1, "S3"),
    ],
)
def test_cross_check_expectations(
    case: CaseFile,
    evidence_ids: list[str],
    expected_type: str | None,
    expected_count: int,
    person: str | None,
) -> None:
    # 교차 검증 실행
    result = cross_check_evidence(case, evidence_ids)
    # 전체 관계 건수 확인
    assert len(result.relations) == expected_count
    # 모든 관계의 종류와 인물 확인
    for relation in result.relations:
        assert relation.type == expected_type
        assert relation.person_ids == [person]


# 공개 정보 정답 미노출 테스트
# 공개 정보에 증거 ID·봉인 번호·증거 요약 문장이 없고 소개문의 유물번호는 있는지 확인하는 함수
def test_public_case_hides_answers(case: CaseFile) -> None:
    # 공개 정보 JSON 문자열 (한글 그대로)
    public_json = CaseRepository().get_public_case(CASE_ID).model_dump_json()
    # 증거 ID E1~E23이 단어 단위로 없어야 함
    for number in range(1, 24):
        assert re.search(rf"\bE{number}\b", public_json) is None, f"E{number}"
    # 증거에만 있는 봉인 번호가 없어야 함
    assert "SG-0392" not in public_json
    # 증거 요약 문장이 없어야 함
    for item in case.evidence:
        assert item.summary not in public_json, item.id
    # 소개문의 유물번호는 공개 정보라 포함
    assert "HM-112" in public_json
