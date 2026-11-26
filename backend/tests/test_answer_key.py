from pathlib import Path

import pytest

from app.schemas.answer import AnswerKey
from app.schemas.case import CaseFile
from app.services.answer_key import load_answer_key, validate_answer_against_case
from app.services.case_repository import CaseDataError, CaseRepository

# 테스트용 가짜 사건·정답 폴더
FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURE_CASES_DIR = FIXTURES_DIR / "cases"
FIXTURE_ANSWERS_DIR = FIXTURES_DIR / "answers"
# 테스트용 가짜 사건 ID
FIXTURE_CASE_ID = "CASE-999"


# 가짜 사건 픽스처
# 가짜 사건 파일을 로드해 반환하는 함수
@pytest.fixture
def case() -> CaseFile:
    # 가짜 사건 폴더에서 사건 로드
    return CaseRepository(FIXTURE_CASES_DIR).load_case(FIXTURE_CASE_ID)


# 가짜 정답 픽스처
# 가짜 정답 파일을 로드해 반환하는 함수
@pytest.fixture
def answer() -> AnswerKey:
    # 가짜 정답 폴더에서 정답 로드
    return load_answer_key(FIXTURE_CASE_ID, FIXTURE_ANSWERS_DIR)


# 정상 정답 테스트
# 가짜 정답이 로드되고 사건과의 대조 검증을 통과하는지 확인하는 함수
def test_load_and_validate_answer(answer: AnswerKey, case: CaseFile) -> None:
    # 정답 내용 확인
    assert answer.case_id == FIXTURE_CASE_ID
    assert answer.culprit_id == "S1"
    assert answer.decisive_evidence_ids == ["E2", "E3"]
    # 대조 검증이 예외 없이 통과해야 함
    validate_answer_against_case(answer, case)


# 없는 증거 ID 테스트
# 정답이 사건에 없는 증거를 가리키면 CaseDataError가 나는지 확인하는 함수
def test_rejects_unknown_evidence(answer: AnswerKey, case: CaseFile) -> None:
    # 결정적 증거에 없는 ID 넣기
    broken = answer.model_copy(update={"decisive_evidence_ids": ["E2", "E99"]})
    # 검증 실패 확인
    with pytest.raises(CaseDataError):
        validate_answer_against_case(broken, case)


# 없는 용의자 테스트
# 범인이 용의자 목록에 없으면 CaseDataError가 나는지 확인하는 함수
def test_rejects_unknown_culprit(answer: AnswerKey, case: CaseFile) -> None:
    # 범인을 없는 용의자로 변경
    broken = answer.model_copy(update={"culprit_id": "S9"})
    # 검증 실패 확인
    with pytest.raises(CaseDataError):
        validate_answer_against_case(broken, case)


# 결정적·오해 유발 증거 겹침 테스트
# 같은 증거가 결정적 증거와 오해 유발 증거에 모두 있으면 CaseDataError가 나는지 확인하는 함수
def test_rejects_overlapping_evidence(answer: AnswerKey, case: CaseFile) -> None:
    # 오해 유발 증거에 결정적 증거 E2 넣기
    broken = answer.model_copy(update={"misleading_evidence_ids": ["E2"]})
    # 검증 실패 확인
    with pytest.raises(CaseDataError):
        validate_answer_against_case(broken, case)
