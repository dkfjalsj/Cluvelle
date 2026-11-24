import re
from pathlib import Path

import pytest

from app.schemas.case import CaseFile
from app.schemas.tool import InvestigationResult
from app.services.case_repository import CaseRepository
from app.tools import (
    ToolArgumentError,
    check_cctv,
    inspect_scene,
    interview_suspect,
    verify_alibi,
)

# 테스트용 가짜 사건 폴더
FIXTURE_CASES_DIR = Path(__file__).parent / "fixtures" / "cases"
# 조사 도구 소스 폴더
TOOLS_DIR = Path(__file__).resolve().parents[1] / "app" / "tools"
# 결과 JSON에 들어가면 안 되는 문자열
FORBIDDEN_RESULT_WORDS = ("facts", "culprit", "decisive", "misleading", "solution")


# 가짜 사건 픽스처
# 테스트용 CASE-999를 로드해 반환하는 함수
@pytest.fixture
def fake_case() -> CaseFile:
    # 가짜 사건 폴더에서 로드
    return CaseRepository(FIXTURE_CASES_DIR).load_case("CASE-999")


# CASE-001 픽스처
# 기본 경로에서 CASE-001을 로드해 반환하는 함수
@pytest.fixture
def case_001() -> CaseFile:
    # 기본 사건 폴더에서 로드
    return CaseRepository().load_case("CASE-001")


# 결과 증거 ID 추출
# 조회 도구 결과에서 증거 ID 목록을 순서대로 뽑아 반환하는 함수
def evidence_ids(result: InvestigationResult) -> list[str]:
    # 증거 ID만 모아 반환
    return [item.id for item in result.evidence]


# 빈 결과 확인
# 결과가 증거 없음(특이사항 없음) 형태인지 확인하는 함수
def assert_nothing_found(result: InvestigationResult) -> None:
    # 발견 없음, 빈 목록, 고정 문구 확인
    assert result.found is False
    assert result.evidence == []
    assert result.message == "특이사항 없음"


# 현장 조사 테스트
# 증거 있는 장소는 해당 증거를, 없는 장소는 특이사항 없음을 반환하는지 확인하는 함수
def test_inspect_scene(fake_case: CaseFile, case_001: CaseFile) -> None:
    # 증거가 있는 장소
    result = inspect_scene(fake_case, "L1")
    assert result.found is True
    assert evidence_ids(result) == ["E1"]
    assert result.args == {"location_id": "L1"}
    assert result.message == "증거 1건을 확보했습니다."
    # 증거가 없는 장소 (CASE-001 휴게실)
    assert_nothing_found(inspect_scene(case_001, "L4"))


# 용의자 심문 테스트
# 증거 있는 용의자·주제는 진술 증거를, 없는 조합은 특이사항 없음을 반환하는지 확인하는 함수
def test_interview_suspect(fake_case: CaseFile) -> None:
    # 증거가 있는 조합
    result = interview_suspect(fake_case, "S1", "T1")
    assert result.found is True
    assert evidence_ids(result) == ["E2"]
    assert result.args == {"suspect_id": "S1", "topic_id": "T1"}
    # 증거가 없는 조합
    assert_nothing_found(interview_suspect(fake_case, "S1", "T2"))


# CCTV 확인 테스트
# 증거 있는 카메라·시간대는 CCTV 증거를, 없는 조합은 특이사항 없음을 반환하는지 확인하는 함수
def test_check_cctv(fake_case: CaseFile) -> None:
    # 증거가 있는 시간대
    result = check_cctv(fake_case, "C1", "21:00-22:00")
    assert result.found is True
    assert evidence_ids(result) == ["E3"]
    assert result.args == {"camera_id": "C1", "time_window": "21:00-22:00"}
    # 증거가 없는 시간대
    assert_nothing_found(check_cctv(fake_case, "C1", "20:00-21:00"))


# 알리바이 확인 테스트
# 기록 있는 용의자는 알리바이 증거를, 없는 용의자는 특이사항 없음을 반환하는지 확인하는 함수
def test_verify_alibi(fake_case: CaseFile) -> None:
    # 기록이 있는 용의자
    result = verify_alibi(fake_case, "S2")
    assert result.found is True
    assert evidence_ids(result) == ["E4"]
    assert result.args == {"suspect_id": "S2"}
    # 기록이 없는 용의자
    assert_nothing_found(verify_alibi(fake_case, "S1"))


# 잘못된 인자 테스트
# 공개 목록에 없는 장소·용의자·주제·카메라와 카메라에 없는 시간대를 거부하는지 확인하는 함수
def test_invalid_arguments(fake_case: CaseFile) -> None:
    # 없는 장소
    with pytest.raises(ToolArgumentError, match="L9"):
        inspect_scene(fake_case, "L9")
    # 없는 용의자 (심문·알리바이)
    with pytest.raises(ToolArgumentError, match="S9"):
        interview_suspect(fake_case, "S9", "T1")
    with pytest.raises(ToolArgumentError, match="S9"):
        verify_alibi(fake_case, "S9")
    # 없는 주제
    with pytest.raises(ToolArgumentError, match="T9"):
        interview_suspect(fake_case, "S1", "T9")
    # 없는 카메라
    with pytest.raises(ToolArgumentError, match="C9"):
        check_cctv(fake_case, "C9", "20:00-21:00")
    # 카메라에 없는 시간대
    with pytest.raises(ToolArgumentError, match="22:00-23:00"):
        check_cctv(fake_case, "C1", "22:00-23:00")


# CASE-001 전체 조합 실행
# CASE-001의 공개 선택지로 만들 수 있는 30개 조합을 모두 호출해 결과 목록을 반환하는 함수
def run_all_combos(case: CaseFile) -> list[InvestigationResult]:
    # 결과 목록
    results: list[InvestigationResult] = []
    # 현장 조사: 장소마다
    for location in case.locations:
        results.append(inspect_scene(case, location.id))
    # 심문: 용의자 × 주제
    for suspect in case.suspects:
        for topic in case.topics:
            results.append(interview_suspect(case, suspect.id, topic.id))
    # CCTV: 카메라 × 시간대
    for camera in case.cameras:
        for window in camera.time_windows:
            results.append(check_cctv(case, camera.id, window))
    # 알리바이: 용의자마다
    for suspect in case.suspects:
        results.append(verify_alibi(case, suspect.id))
    # 결과 반환
    return results


# CASE-001 전체 조합 테스트
# 30개 조합 중 22개만 증거가 나오고 증거 ID 합집합이 E1~E22와 같은지 확인하는 함수
def test_case_001_all_combos(case_001: CaseFile) -> None:
    # 전체 조합 실행
    results = run_all_combos(case_001)
    assert len(results) == 30
    # 발견 여부별 개수 확인
    assert sum(result.found for result in results) == 22
    assert sum(not result.found for result in results) == 8
    # 반환된 증거 ID 합집합 확인
    found_ids = {item.id for result in results for item in result.evidence}
    assert found_ids == {f"E{number}" for number in range(1, 23)}


# 결과 JSON 정답 미노출 테스트
# 모든 조회 결과 JSON에 사실 관계·정답 관련 문자열이 없는지 확인하는 함수
def test_results_have_no_hidden_fields(case_001: CaseFile) -> None:
    # 모든 조합 결과 검사
    for result in run_all_combos(case_001):
        result_json = result.model_dump_json()
        # 금지 문자열이 하나도 없어야 함
        for word in FORBIDDEN_RESULT_WORDS:
            assert word not in result_json, (word, result.args)


# 정답 모듈 미참조 테스트
# app/tools 아래 모든 소스가 정답 모듈·폴더를 import하지 않는지 확인하는 함수
def test_tools_do_not_import_answers() -> None:
    # import 줄 중 answer가 들어간 줄을 찾는 정규식
    pattern = re.compile(r"^\s*(from|import)\s+[^\n]*answer", re.MULTILINE)
    # 도구 폴더의 모든 파이썬 파일 검사
    sources = list(TOOLS_DIR.rglob("*.py"))
    assert sources
    for path in sources:
        source = path.read_text(encoding="utf-8")
        # answer 관련 import가 없어야 함
        assert pattern.search(source) is None, path.name
