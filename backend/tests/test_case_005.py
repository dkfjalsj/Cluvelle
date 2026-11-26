import re
from collections import Counter

import pytest

from app.schemas.answer import AnswerKey
from app.schemas.case import CaseFile
from app.services.answer_key import load_answer_key, validate_answer_against_case
from app.services.case_repository import CaseRepository
from app.services.case_validation import validate_case
from app.tools import cross_check_evidence

# 검증 대상 사건 ID
CASE_ID = "CASE-005"
# 설명이 있어야 하는 장소·카메라와 그 값
LOCATION_DESCRIPTIONS = {
    "L1": "소품 테이블과 시계 트레이가 있고 무대와 바로 이어짐",
    "L2": "철망 문으로 잠김",
    "L3": "무대감독 콘솔이 무대 오른쪽 끝에 있음",
    "L4": "배우 분장과 대기",
    "L5": "윙·소품 창고·분장실·무대 오른쪽 출입구로 이어짐",
}
CAMERA_DESCRIPTIONS = {
    "C1": "소품 창고 철망 문과 분장실 문이 보임",
    "C2": "윙 출입문 위 근접 설치. 무대 쪽 진입로도 보이고, 소품 테이블은 커튼에 가려 보이지 않음",
}
# 사실 관계가 없는 증거
EVIDENCE_WITHOUT_FACTS = {
    "E1",
    "E2",
    "E3",
    "E5",
    "E6",
    "E7",
    "E9",
    "E11",
    "E13",
    "E14",
    "E25",
}


# 사건 픽스처
# 기본 경로에서 CASE-005 사건을 로드해 반환하는 함수
@pytest.fixture
def case() -> CaseFile:
    # 기본 사건 폴더에서 로드
    return CaseRepository().load_case(CASE_ID)


# 정답 픽스처
# 기본 경로에서 CASE-005 정답을 로드해 반환하는 함수
@pytest.fixture
def answer() -> AnswerKey:
    # 기본 정답 폴더에서 로드
    return load_answer_key(CASE_ID)


# 로드 및 정답 대조 테스트
# CASE-005 사건·정답이 로드되고 대조 검증을 통과하는지 확인하는 함수
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
    assert all(len(camera.time_windows) == 3 for camera in case.cameras)
    assert len(case.topics) == 4
    assert len(case.evidence) == 25


# 기본 정보 테스트
# 난이도와 사건 밖 표기가 설계와 같은지 확인하는 함수
def test_basic_info(case: CaseFile) -> None:
    # 난이도와 표기 확인
    assert case.difficulty == "challenge"
    assert case.off_site_label == "극장 밖"


# 설명 필드 테스트
# 설명이 표에 있는 장소·카메라에만 있고 값이 같으며 L6·C3에는 없는지 확인하는 함수
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
    assert cameras["C3"].description is None


# 사실 관계 없는 증거 테스트
# 사실 관계가 없는 증거가 정확히 지정한 11개인지 확인하는 함수
def test_evidence_without_facts(case: CaseFile) -> None:
    # 사실 관계가 빈 증거 ID 집합
    empty = {item.id for item in case.evidence if not item.facts}
    assert empty == EVIDENCE_WITHOUT_FACTS


# 신원 미상 기록 테스트
# E17의 20:24·20:25 사실은 인물이 지정되지 않았는지 확인하는 함수
def test_unidentified_facts(case: CaseFile) -> None:
    # E17 사실 목록
    evidence_by_id = {item.id: item for item in case.evidence}
    facts = evidence_by_id["E17"].facts
    # 20:24·20:25 사실 찾기
    targets = [fact for fact in facts if fact.start in ("20:24", "20:25")]
    assert len(targets) == 2
    # 모두 person_id가 null
    assert all(fact.person_id is None for fact in targets)


# 사건 검증 테스트
# 사건 검증 규칙을 모두 통과하고 통계가 설계값과 같은지 확인하는 함수
def test_validate_case(case: CaseFile, answer: AnswerKey) -> None:
    # 검증 실행
    report = validate_case(case, answer)
    assert report.passed, report.errors
    stats = report.stats
    assert stats is not None
    # 설계값 확인
    assert stats.combo_count == 30
    assert stats.combos_with_evidence == 25
    assert stats.combos_without_evidence == 5
    assert stats.decisive_count == 3
    assert stats.misleading_count == 2
    assert stats.path_length == 6


# 교차 검증 기대값 테스트
# 증거 조합마다 관계의 (종류, 인물) 구성과 건수가 설계와 정확히 같은지 확인하는 함수
@pytest.mark.parametrize(
    ("evidence_ids", "expected"),
    [
        (["E12", "E20"], {("same_person_overlap_different_place", ("S3",)): 2}),
        (["E12", "E25"], {}),
        (["E15", "E23"], {("same_person_overlap_different_place", ("S1",)): 1}),
        (["E4", "E23"], {("same_person_overlap_different_place", ("S1",)): 1}),
        (
            ["E4", "E17"],
            {
                ("same_person_overlap_different_place", ("S1",)): 2,
                ("unidentified_time_overlap", ("S1",)): 2,
            },
        ),
        (["E15", "E17"], {("unidentified_time_overlap", ("S1",)): 1}),
        (["E8", "E24"], {("same_person_overlap_same_place", ("S2",)): 1}),
        (["E10", "E23"], {("same_person_overlap_same_place", ("S1",)): 1}),
    ],
)
def test_cross_check_expectations(
    case: CaseFile,
    evidence_ids: list[str],
    expected: dict[tuple[str, tuple[str, ...]], int],
) -> None:
    # 교차 검증 실행
    result = cross_check_evidence(case, evidence_ids)
    # (종류, 인물)별 건수 집계 후 비교 (총 건수도 함께 일치)
    actual = Counter(
        (relation.type, tuple(relation.person_ids)) for relation in result.relations
    )
    assert dict(actual) == expected


# 공개 정보 정답 미노출 테스트
# 공개 정보에 증거 ID·증거 요약 문장·확인자 이름이 없고 소개문의 소품 번호는 있는지 확인하는 함수
def test_public_case_hides_answers(case: CaseFile) -> None:
    # 공개 정보 JSON 문자열 (한글 그대로)
    public_json = CaseRepository().get_public_case(CASE_ID).model_dump_json()
    # 증거 ID E1~E25가 단어 단위로 없어야 함
    for number in range(1, 26):
        assert re.search(rf"\bE{number}\b", public_json) is None, f"E{number}"
    # 증거 요약 문장이 없어야 함
    for item in case.evidence:
        assert item.summary not in public_json, item.id
    # 증거에만 나오는 확인자 이름이 없어야 함
    assert "오세라" not in public_json
    # 소개문의 소품 번호는 공개 정보라 포함
    assert "P-14B" in public_json
