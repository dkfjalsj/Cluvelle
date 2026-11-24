import copy
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.schemas.case import CaseFile
from app.services.case_repository import (
    CaseNotFoundError,
    CaseRepository,
    InvalidCaseIdError,
)

# 테스트용 가짜 사건 폴더
FIXTURE_CASES_DIR = Path(__file__).parent / "fixtures" / "cases"
# 테스트용 가짜 사건 ID
FIXTURE_CASE_ID = "CASE-999"


# 저장소 픽스처
# 가짜 사건 폴더를 읽는 사건 저장소를 만드는 함수
@pytest.fixture
def repository() -> CaseRepository:
    # 가짜 사건 폴더로 저장소 생성
    return CaseRepository(FIXTURE_CASES_DIR)


# 가짜 사건 원본 픽스처
# 가짜 사건 JSON을 수정 가능한 dict로 읽어 반환하는 함수
@pytest.fixture
def raw_case() -> dict[str, Any]:
    # 가짜 사건 파일을 읽어 dict로 변환
    path = FIXTURE_CASES_DIR / f"{FIXTURE_CASE_ID}.json"
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    # 테스트마다 독립적으로 수정하도록 깊은 복사본 반환
    return copy.deepcopy(data)


# 정상 로드 테스트
# 가짜 사건이 검증을 통과해 올바른 내용으로 로드되는지 확인하는 함수
def test_load_case_returns_valid_case(repository: CaseRepository) -> None:
    # 가짜 사건 로드
    case = repository.load_case(FIXTURE_CASE_ID)
    # 기본 정보 확인
    assert case.case_id == FIXTURE_CASE_ID
    assert case.difficulty == "intro"
    assert case.tool_budget == 10
    # 구성 개수 확인
    assert len(case.suspects) == 3
    assert len(case.locations) == 2
    assert len(case.cameras) == 1
    assert len(case.topics) == 2
    assert len(case.evidence) == 5


# 사건 ID 목록 테스트
# 폴더의 사건 파일에서 ID 목록을 정렬해 반환하는지 확인하는 함수
def test_list_case_ids(repository: CaseRepository) -> None:
    # 가짜 사건 하나만 있어야 함
    assert repository.list_case_ids() == [FIXTURE_CASE_ID]


# 사건 요약 목록 테스트
# 요약 목록이 ID·제목·난이도·한 줄 소개를 담는지 확인하는 함수
def test_list_summaries(repository: CaseRepository) -> None:
    # 요약 목록 조회
    summaries = repository.list_summaries()
    # 하나의 요약과 그 내용 확인
    assert len(summaries) == 1
    assert summaries[0].case_id == FIXTURE_CASE_ID
    assert summaries[0].title == "테스트 창고 상자 분실"
    assert summaries[0].difficulty == "intro"
    assert summaries[0].summary == "테스트용 창고에서 상자 하나가 사라졌다."


# 잘못된 ID 형식 테스트
# 형식이 틀리거나 경로 조작이 섞인 ID를 InvalidCaseIdError로 거부하는지 확인하는 함수
@pytest.mark.parametrize("case_id", ["case-1", "../x", "CASE-12"])
def test_load_case_rejects_invalid_id(repository: CaseRepository, case_id: str) -> None:
    # 형식 오류 예외 발생 확인
    with pytest.raises(InvalidCaseIdError):
        repository.load_case(case_id)


# 없는 사건 테스트
# 형식은 맞지만 파일이 없는 ID를 CaseNotFoundError로 거부하는지 확인하는 함수
def test_load_case_rejects_missing_case(repository: CaseRepository) -> None:
    # 파일 없음 예외 발생 확인
    with pytest.raises(CaseNotFoundError):
        repository.load_case("CASE-998")


# 증거 ID 중복 테스트
# 같은 증거 ID가 두 번 있으면 검증에 실패하는지 확인하는 함수
def test_rejects_duplicate_evidence_id(raw_case: dict[str, Any]) -> None:
    # 두 번째 증거의 ID를 첫 번째와 같게 변경
    raw_case["evidence"][1]["id"] = "E1"
    # 검증 실패 확인
    with pytest.raises(ValidationError):
        CaseFile.model_validate(raw_case)


# 없는 장소 locator 테스트
# 증거 locator가 존재하지 않는 장소를 가리키면 검증에 실패하는지 확인하는 함수
def test_rejects_locator_with_unknown_location(raw_case: dict[str, Any]) -> None:
    # 현장 증거의 장소를 없는 ID로 변경
    raw_case["evidence"][0]["locator"]["location_id"] = "L9"
    # 검증 실패 확인
    with pytest.raises(ValidationError):
        CaseFile.model_validate(raw_case)


# 도구와 맞지 않는 locator 테스트
# source_tool에 필요 없는 locator 필드가 있으면 검증에 실패하는지 확인하는 함수
def test_rejects_locator_fields_not_matching_tool(raw_case: dict[str, Any]) -> None:
    # 현장 조사 증거에 용의자 필드를 추가
    raw_case["evidence"][0]["locator"]["suspect_id"] = "S1"
    # 검증 실패 확인
    with pytest.raises(ValidationError):
        CaseFile.model_validate(raw_case)


# 카메라에 없는 시간대 테스트
# CCTV 증거의 시간대가 카메라 조회 가능 시간대에 없으면 검증에 실패하는지 확인하는 함수
def test_rejects_time_window_not_in_camera(raw_case: dict[str, Any]) -> None:
    # CCTV 증거의 시간대를 카메라에 없는 구간으로 변경
    raw_case["evidence"][2]["locator"]["time_window"] = "22:00-23:00"
    # 검증 실패 확인
    with pytest.raises(ValidationError):
        CaseFile.model_validate(raw_case)


# 잘못된 시간 형식 테스트
# 사실 관계의 시각이 HH:MM 형식이 아니면 검증에 실패하는지 확인하는 함수
def test_rejects_invalid_time_format(raw_case: dict[str, Any]) -> None:
    # 진술 사실의 시작 시각을 잘못된 형식으로 변경
    raw_case["evidence"][1]["facts"][0]["start"] = "8:00"
    # 검증 실패 확인
    with pytest.raises(ValidationError):
        CaseFile.model_validate(raw_case)


# 알 수 없는 필드 테스트
# 정의되지 않은 필드가 있으면 검증에 실패하는지 확인하는 함수
def test_rejects_unknown_field(raw_case: dict[str, Any]) -> None:
    # 최상위에 정의되지 않은 필드 추가
    raw_case["culprit_id"] = "S1"
    # 검증 실패 확인
    with pytest.raises(ValidationError):
        CaseFile.model_validate(raw_case)


# off_site 표기 누락 테스트
# off_site_label이 없으면 검증에 실패하는지 확인하는 함수
def test_rejects_missing_off_site_label(raw_case: dict[str, Any]) -> None:
    # off_site_label 필드 삭제
    del raw_case["off_site_label"]
    # 검증 실패 확인
    with pytest.raises(ValidationError):
        CaseFile.model_validate(raw_case)


# off_site 표기 빈 값 테스트
# off_site_label이 빈 문자열이거나 공백만 있으면 검증에 실패하는지 확인하는 함수
@pytest.mark.parametrize("label", ["", "   "])
def test_rejects_blank_off_site_label(raw_case: dict[str, Any], label: str) -> None:
    # off_site_label을 빈 값으로 변경
    raw_case["off_site_label"] = label
    # 검증 실패 확인
    with pytest.raises(ValidationError):
        CaseFile.model_validate(raw_case)
