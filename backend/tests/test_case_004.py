import re

import pytest

from app.schemas.answer import AnswerKey
from app.schemas.case import CaseFile
from app.services.answer_key import load_answer_key, validate_answer_against_case
from app.services.case_repository import CaseRepository
from app.services.case_validation import validate_case
from app.tools import cross_check_evidence

# 검증 대상 사건 ID
CASE_ID = "CASE-004"
# 설명이 있어야 하는 장소·카메라와 그 값
LOCATION_DESCRIPTIONS = {
    "L1": "레시피 원본 파일이 있는 공용 PC",
    "L2": "사장실·휴게실·창고로 이어짐",
    "L3": "에스프레소 머신과 계산대",
    "L4": "문 옆에 공유 프린터",
    "L5": "뒷문 있음",
}
CAMERA_DESCRIPTIONS = {
    "C2": "사장실 문과 휴게실 문 옆 공유 프린터까지 보이는 근접 설치",
}


# 사건 픽스처
# 기본 경로에서 CASE-004 사건을 로드해 반환하는 함수
@pytest.fixture
def case() -> CaseFile:
    # 기본 사건 폴더에서 로드
    return CaseRepository().load_case(CASE_ID)


# 정답 픽스처
# 기본 경로에서 CASE-004 정답을 로드해 반환하는 함수
@pytest.fixture
def answer() -> AnswerKey:
    # 기본 정답 폴더에서 로드
    return load_answer_key(CASE_ID)


# 로드 및 정답 대조 테스트
# CASE-004 사건·정답이 로드되고 대조 검증을 통과하는지 확인하는 함수
def test_case_and_answer_load(case: CaseFile, answer: AnswerKey) -> None:
    # 기본 정보 확인
    assert case.case_id == CASE_ID
    assert answer.culprit_id == "S3"
    # 대조 검증이 예외 없이 통과해야 함
    validate_answer_against_case(answer, case)


# 구성 개수 테스트
# 용의자·장소·카메라·시간대·주제·증거 개수가 설계와 같은지 확인하는 함수
def test_case_counts(case: CaseFile) -> None:
    # 종류별 개수 확인
    assert len(case.suspects) == 3
    assert len(case.locations) == 6
    assert len(case.cameras) == 3
    assert all(len(camera.time_windows) == 4 for camera in case.cameras)
    assert len(case.topics) == 4
    assert len(case.evidence) == 23


# 기본 정보 테스트
# 난이도와 사건 밖 표기가 설계와 같은지 확인하는 함수
def test_basic_info(case: CaseFile) -> None:
    # 난이도와 표기 확인
    assert case.difficulty == "normal"
    assert case.off_site_label == "매장 밖"


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
    assert locations["L6"].description is None
    assert cameras["C1"].description is None
    assert cameras["C3"].description is None


# 사건 검증 테스트
# 사건 검증 규칙을 모두 통과하고 통계가 설계값과 같은지 확인하는 함수
def test_validate_case(case: CaseFile, answer: AnswerKey) -> None:
    # 검증 실행
    report = validate_case(case, answer)
    assert report.passed, report.errors
    stats = report.stats
    assert stats is not None
    # 설계값 확인
    assert stats.combo_count == 33
    assert stats.combos_with_evidence == 23
    assert stats.combos_without_evidence == 10
    assert stats.decisive_count == 3
    assert stats.misleading_count == 2
    assert stats.path_length == 6


# 교차 검증 기대값 테스트
# 증거 조합마다 관계의 (종류, 인물) 목록이 설계와 순서까지 정확히 같은지 확인하는 함수
@pytest.mark.parametrize(
    ("evidence_ids", "expected"),
    [
        (
            ["E11", "E18"],
            [("same_person_overlap_different_place", ["S3"])] * 4,
        ),
        (["E11", "E19"], [("same_person_overlap_same_place", ["S3"])] * 2),
        # E15의 S2 계산대 기록과 E4의 S1 진술이 겹쳐 서로 다른 인물 관계가 1건 더 나옴
        (
            ["E4", "E15"],
            [
                ("same_person_overlap_same_place", ["S1"]),
                ("different_people_same_place_overlap", ["S1", "S2"]),
            ],
        ),
        (["E4", "E21"], [("same_person_overlap_same_place", ["S1"])] * 3),
        (["E10", "E18"], []),
        (["E7", "E22"], [("same_person_overlap_same_place", ["S2"])]),
    ],
)
def test_cross_check_expectations(
    case: CaseFile,
    evidence_ids: list[str],
    expected: list[tuple[str, list[str]]],
) -> None:
    # 교차 검증 실행
    result = cross_check_evidence(case, evidence_ids)
    # 관계의 (종류, 인물) 목록 비교
    actual = [(relation.type, relation.person_ids) for relation in result.relations]
    assert actual == expected


# 공개 정보 정답 미노출 테스트
# 공개 정보에 증거 ID·증거 요약 문장이 없고 소개문의 출력 번호는 있는지 확인하는 함수
def test_public_case_hides_answers(case: CaseFile) -> None:
    # 공개 정보 JSON 문자열 (한글 그대로)
    public_json = CaseRepository().get_public_case(CASE_ID).model_dump_json()
    # 증거 ID E1~E23이 단어 단위로 없어야 함
    for number in range(1, 24):
        assert re.search(rf"\bE{number}\b", public_json) is None, f"E{number}"
    # 증거 요약 문장이 없어야 함
    for item in case.evidence:
        assert item.summary not in public_json, item.id
    # 소개문의 출력 번호는 공개 정보라 포함
    assert "#0018" in public_json
