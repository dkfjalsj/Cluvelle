import re

import pytest

from app.schemas.answer import AnswerKey
from app.schemas.case import CaseFile, EvidenceLocator
from app.services.answer_key import load_answer_key, validate_answer_against_case
from app.services.case_repository import CaseRepository

# 검증 대상 사건 ID
CASE_ID = "CASE-001"

# 조회 조합 하나를 나타내는 키 (도구 이름, 정렬된 locator 항목)
ComboKey = tuple[str, tuple[tuple[str, str], ...]]


# 사건 픽스처
# 기본 경로의 저장소에서 CASE-001을 로드해 반환하는 함수
@pytest.fixture
def case() -> CaseFile:
    # 기본 사건 폴더로 로드
    return CaseRepository().load_case(CASE_ID)


# 정답 픽스처
# 기본 경로에서 CASE-001 정답 키를 로드해 반환하는 함수
@pytest.fixture
def answer() -> AnswerKey:
    # 기본 정답 폴더로 로드
    return load_answer_key(CASE_ID)


# 조합 키 생성
# 도구 이름과 locator 값으로 비교 가능한 조합 키를 만드는 함수
def make_combo_key(tool: str, locator: dict[str, str]) -> ComboKey:
    # locator 항목을 정렬해 순서와 무관하게 비교되도록 함
    return tool, tuple(sorted(locator.items()))


# 전체 조사 조합 생성
# 사건의 공개 선택지로 만들 수 있는 모든 조사 조합 키를 반환하는 함수
def build_all_combos(case: CaseFile) -> set[ComboKey]:
    # 조합 키 집합
    combos: set[ComboKey] = set()
    # 현장 조사: 장소마다 1개
    for location in case.locations:
        combos.add(make_combo_key("inspect_scene", {"location_id": location.id}))
    # 심문: 용의자 × 주제
    for suspect in case.suspects:
        for topic in case.topics:
            combos.add(
                make_combo_key(
                    "interview_suspect",
                    {"suspect_id": suspect.id, "topic_id": topic.id},
                )
            )
    # CCTV: 카메라 × 시간대
    for camera in case.cameras:
        for window in camera.time_windows:
            combos.add(
                make_combo_key(
                    "check_cctv", {"camera_id": camera.id, "time_window": window}
                )
            )
    # 알리바이: 용의자마다 1개
    for suspect in case.suspects:
        combos.add(make_combo_key("verify_alibi", {"suspect_id": suspect.id}))
    # 전체 조합 반환
    return combos


# locator 조합 키 변환
# 증거 locator를 값이 있는 필드만 담은 조합 키로 바꾸는 함수
def locator_to_combo_key(tool: str, locator: EvidenceLocator) -> ComboKey:
    # 값이 있는 필드만 사용
    values = {
        key: str(value) for key, value in locator.model_dump(exclude_none=True).items()
    }
    # 조합 키 생성
    return make_combo_key(tool, values)


# 로드 및 정답 대조 테스트
# CASE-001과 정답이 로드되고 대조 검증을 통과하는지 확인하는 함수
def test_case_and_answer_load(case: CaseFile, answer: AnswerKey) -> None:
    # 기본 정보 확인
    assert case.case_id == CASE_ID
    assert case.off_site_label == "연구동 밖"
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
    assert len(case.evidence) == 22


# 조사 조합 수 테스트
# 전체 조사 조합이 30개이고 그중 결과 없는 조합이 8개인지 확인하는 함수
def test_combo_counts(case: CaseFile) -> None:
    # 공식으로 계산한 조합 수 확인
    formula_count = (
        len(case.locations)
        + len(case.suspects) * len(case.topics)
        + sum(len(camera.time_windows) for camera in case.cameras)
        + len(case.suspects)
    )
    assert formula_count == 30
    # 실제 조합 집합 생성
    all_combos = build_all_combos(case)
    assert len(all_combos) == 30
    # 증거가 있는 조합 집합
    combos_with_evidence = {
        locator_to_combo_key(item.source_tool, item.locator) for item in case.evidence
    }
    # 증거 조합은 모두 공개 선택지 안에 있어야 함
    assert combos_with_evidence <= all_combos
    # 결과 없는 조합 수 확인
    assert len(all_combos - combos_with_evidence) == 8


# 정답 구성 테스트
# 결정적 증거 3개, 오해 유발 증거 2개, 해결 경로 5단계 이하인지 확인하는 함수
def test_answer_counts(answer: AnswerKey) -> None:
    # 개수 확인
    assert len(answer.decisive_evidence_ids) == 3
    assert len(answer.misleading_evidence_ids) == 2
    assert len(answer.solution_path) <= 5


# 해결 경로 인자 테스트
# 해결 경로 1~4단계 인자가 실제 ID·시간대이고 5단계 증거가 존재하는지 확인하는 함수
def test_solution_path_args_exist(case: CaseFile, answer: AnswerKey) -> None:
    # 종류별 유효 ID 집합
    valid_ids: dict[str, set[str]] = {
        "location_id": {location.id for location in case.locations},
        "suspect_id": {suspect.id for suspect in case.suspects},
        "topic_id": {topic.id for topic in case.topics},
        "camera_id": {camera.id for camera in case.cameras},
    }
    # 카메라별 시간대 조회 표
    windows_by_camera = {camera.id: camera.time_windows for camera in case.cameras}
    # 1~4단계: 조회 도구 인자 확인
    for step in answer.solution_path[:4]:
        for key, value in step.args.items():
            # 인자 값은 문자열이어야 함
            assert isinstance(value, str), (step.tool, key)
            if key == "time_window":
                # 시간대는 같은 단계의 카메라 시간대 안에 있어야 함
                camera_id = step.args["camera_id"]
                assert isinstance(camera_id, str)
                assert value in windows_by_camera[camera_id], (step.tool, value)
            else:
                # ID는 해당 종류 목록에 있어야 함
                assert value in valid_ids[key], (step.tool, key, value)
    # 5단계: 교차 검증 증거 ID 확인
    last_step = answer.solution_path[4]
    assert last_step.tool == "cross_check_evidence"
    evidence_ids = last_step.args["evidence_ids"]
    assert isinstance(evidence_ids, list)
    assert set(evidence_ids) <= {item.id for item in case.evidence}


# 차량 기록 인물 테스트
# 차량 기록 증거 E17·E18의 모든 사실에 인물이 지정되지 않았는지 확인하는 함수
def test_vehicle_records_have_no_person(case: CaseFile) -> None:
    # 증거 ID 조회 표
    evidence_by_id = {item.id: item for item in case.evidence}
    # 두 차량 기록 확인
    for evidence_id in ("E17", "E18"):
        facts = evidence_by_id[evidence_id].facts
        # 사실이 있어야 하고 모두 person_id가 null이어야 함
        assert facts
        assert all(fact.person_id is None for fact in facts)


# 공개 정보 정답 미노출 테스트
# CASE-001 공개 정보에 증거 ID·자산 태그·정답 문구·증거 요약이 없는지 확인하는 함수
def test_public_case_hides_answers(case: CaseFile) -> None:
    # 공개 정보 JSON 문자열 (한글 그대로)
    public_json = CaseRepository().get_public_case(CASE_ID).model_dump_json()
    # 증거 ID E1~E22가 단어 단위로 등장하지 않아야 함
    for number in range(1, 23):
        assert re.search(rf"\bE{number}\b", public_json) is None, f"E{number}"
    # 증거에만 있는 자산 태그가 없어야 함
    assert "RL-0417" not in public_json
    # 정답 문구가 없어야 함
    assert "S3가 범인" not in public_json
    # 증거 요약 문장이 없어야 함
    for item in case.evidence:
        assert item.summary not in public_json, item.id
    # 도입부의 시제품 이름은 공개 정보라 포함되어 있어야 함
    assert "HAPTIX-1" in public_json
