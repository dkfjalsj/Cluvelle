import re

import pytest

from app.schemas.answer import AnswerKey
from app.schemas.case import CaseFile
from app.services.answer_key import load_answer_key, validate_answer_against_case
from app.services.case_repository import CaseRepository
from app.services.case_validation import validate_case
from app.tools import cross_check_evidence

# 검증 대상 사건 ID
CASE_ID = "CASE-003"
# 설명이 있어야 하는 장소·카메라와 그 값
LOCATION_DESCRIPTIONS = {
    "L1": "피해 객실, 금고 있음",
    "L2": "엘리베이터 홀과 제빙기가 있음",
    "L3": "직원용 엘리베이터 바로 앞",
    "L4": "1층",
    "L6": "지하 1층",
    "L7": "배승현의 객실",
}
CAMERA_DESCRIPTIONS = {
    "C1": "프런트 데스크가 보임",
    "C2": "1207~1209호 쪽 복도 끝은 보이지 않음",
    "C3": "엘리베이터 내부 근접 촬영",
}


# 사건 픽스처
# 기본 경로에서 CASE-003 사건을 로드해 반환하는 함수
@pytest.fixture
def case() -> CaseFile:
    # 기본 사건 폴더에서 로드
    return CaseRepository().load_case(CASE_ID)


# 정답 픽스처
# 기본 경로에서 CASE-003 정답을 로드해 반환하는 함수
@pytest.fixture
def answer() -> AnswerKey:
    # 기본 정답 폴더에서 로드
    return load_answer_key(CASE_ID)


# 로드 및 정답 대조 테스트
# CASE-003 사건·정답이 로드되고 대조 검증을 통과하는지 확인하는 함수
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
    assert all(len(camera.time_windows) == 4 for camera in case.cameras)
    assert len(case.topics) == 4
    assert len(case.evidence) == 26


# 기본 정보 테스트
# 난이도와 사건 밖 표기가 설계와 같은지 확인하는 함수
def test_basic_info(case: CaseFile) -> None:
    # 난이도와 표기 확인
    assert case.difficulty == "normal"
    assert case.off_site_label == "호텔 밖"


# 설명 필드 테스트
# 설명이 표에 있는 장소·카메라에만 있고 값이 같으며 L5에는 없는지 확인하는 함수
def test_descriptions(case: CaseFile) -> None:
    # 장소 설명 확인 (없어야 하는 장소는 None)
    for location in case.locations:
        assert location.description == LOCATION_DESCRIPTIONS.get(location.id)
    # 카메라 설명 확인
    for camera in case.cameras:
        assert camera.description == CAMERA_DESCRIPTIONS[camera.id]
    # 설명 없는 장소 명시 확인
    locations = {location.id: location for location in case.locations}
    assert locations["L5"].description is None


# 사건 검증 테스트
# 사건 검증 규칙을 모두 통과하고 통계가 설계값과 같은지 확인하는 함수
def test_validate_case(case: CaseFile, answer: AnswerKey) -> None:
    # 검증 실행
    report = validate_case(case, answer)
    assert report.passed, report.errors
    stats = report.stats
    assert stats is not None
    # 설계값 확인
    assert stats.combo_count == 34
    assert stats.combos_with_evidence == 26
    assert stats.combos_without_evidence == 8
    assert stats.decisive_count == 3
    assert stats.misleading_count == 2
    assert stats.path_length == 6


# 신원 미상 진술 테스트
# E8·E15의 모든 사실에 인물이 지정되지 않았는지 확인하는 함수
def test_unidentified_facts(case: CaseFile) -> None:
    # 증거 ID 조회 표
    evidence_by_id = {item.id: item for item in case.evidence}
    # 두 증거 확인
    for evidence_id in ("E8", "E15"):
        facts = evidence_by_id[evidence_id].facts
        # 사실이 있어야 하고 모두 person_id가 null
        assert facts
        assert all(fact.person_id is None for fact in facts)


# 교차 검증 기대값 테스트
# 증거 조합마다 관계 종류·건수·인물이 설계와 정확히 같은지 확인하는 함수
@pytest.mark.parametrize(
    ("evidence_ids", "expected_type", "expected_count", "person_ids"),
    [
        (["E9", "E23"], "same_person_overlap_different_place", 2, ["S2"]),
        (["E9", "E18"], "same_person_overlap_same_place", 2, ["S2"]),
        (["E5", "E24"], "same_person_overlap_same_place", 6, ["S1"]),
        (["E13", "E21"], "same_person_overlap_same_place", 1, ["S3"]),
        (["E13", "E26"], None, 0, None),
        (["E8", "E23"], None, 0, None),
        (["E15", "E5"], "unidentified_time_overlap", 1, ["S1"]),
        (["E15", "E24"], "unidentified_time_overlap", 1, ["S1"]),
    ],
)
def test_cross_check_expectations(
    case: CaseFile,
    evidence_ids: list[str],
    expected_type: str | None,
    expected_count: int,
    person_ids: list[str] | None,
) -> None:
    # 교차 검증 실행
    result = cross_check_evidence(case, evidence_ids)
    # 전체 관계 건수 확인
    assert len(result.relations) == expected_count
    # 모든 관계의 종류와 인물 확인
    for relation in result.relations:
        assert relation.type == expected_type
        assert relation.person_ids == person_ids


# 공개 정보 정답 미노출 테스트
# 공개 정보에 증거 ID·단말 계정·마스터카드 번호·증거 요약 문장이 없는지 확인하는 함수
def test_public_case_hides_answers(case: CaseFile) -> None:
    # 공개 정보 JSON 문자열 (한글 그대로)
    public_json = CaseRepository().get_public_case(CASE_ID).model_dump_json()
    # 증거 ID E1~E26이 단어 단위로 없어야 함
    for number in range(1, 27):
        assert re.search(rf"\bE{number}\b", public_json) is None, f"E{number}"
    # 증거에만 있는 계정·카드 번호가 없어야 함
    assert "FD-07" not in public_json
    assert "HK-03" not in public_json
    # 증거 요약 문장이 없어야 함
    for item in case.evidence:
        assert item.summary not in public_json, item.id
