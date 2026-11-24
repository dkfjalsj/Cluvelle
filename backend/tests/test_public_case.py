import json
import re
from pathlib import Path
from typing import Any

from app.schemas.case import PublicCase
from app.services.case_repository import CaseRepository

# 테스트용 가짜 사건 폴더
FIXTURE_CASES_DIR = Path(__file__).parent / "fixtures" / "cases"
# 테스트용 가짜 사건 ID
FIXTURE_CASE_ID = "CASE-999"
# 공개 정보에 들어가면 안 되는 키 단어
FORBIDDEN_KEY_WORDS = ("evidence", "culprit", "decisive", "solution")
# 공개 정보에 허용되는 필드 집합 (필드가 추가되면 테스트가 실패해야 함)
EXPECTED_PUBLIC_FIELDS = {
    "case_id",
    "version",
    "title",
    "difficulty",
    "summary",
    "introduction",
    "tool_budget",
    "suspects",
    "locations",
    "cameras",
    "topics",
}


# 모든 키 수집
# 중첩된 dict·list를 돌며 등장하는 모든 키 이름을 모아 반환하는 함수
def collect_keys(value: Any) -> set[str]:
    # 수집한 키 집합
    keys: set[str] = set()
    # dict면 키를 모으고 값도 재귀 탐색
    if isinstance(value, dict):
        for key, item in value.items():
            keys.add(key)
            keys |= collect_keys(item)
    # list면 각 항목을 재귀 탐색
    elif isinstance(value, list):
        for item in value:
            keys |= collect_keys(item)
    # 수집 결과 반환
    return keys


# 공개 정보 JSON 생성
# 가짜 사건의 공개 정보를 JSON 문자열로 만들어 반환하는 함수
def build_public_json() -> str:
    # 가짜 사건 저장소에서 공개 정보 조회 후 JSON 변환
    repository = CaseRepository(FIXTURE_CASES_DIR)
    return repository.get_public_case(FIXTURE_CASE_ID).model_dump_json()


# 금지 키 미포함 테스트
# 공개 정보 JSON에 증거·범인·결정적 증거·해결 경로 관련 키가 없는지 확인하는 함수
def test_public_case_has_no_answer_or_evidence_keys() -> None:
    # 공개 JSON의 모든 키 수집
    keys = collect_keys(json.loads(build_public_json()))
    # 금지 단어가 들어간 키가 하나도 없어야 함
    for key in keys:
        for word in FORBIDDEN_KEY_WORDS:
            assert word not in key.lower(), f"공개 정보에 금지 키가 있습니다: {key}"


# 증거 내용 미포함 테스트
# 공개 정보 JSON에 증거 ID와 증거 요약 문장이 하나도 없는지 확인하는 함수
def test_public_case_contains_no_evidence_content() -> None:
    # 공개 JSON 문자열 (한글이 이스케이프되지 않은 형태)
    public_json = build_public_json()
    # 비교용 원본 사건 로드
    case = CaseRepository(FIXTURE_CASES_DIR).load_case(FIXTURE_CASE_ID)
    # 증거마다 ID와 요약 문장이 없어야 함
    for item in case.evidence:
        # 증거 ID가 단어 단위로 등장하지 않아야 함
        assert re.search(rf"\b{item.id}\b", public_json) is None, item.id
        # 증거 요약 문장이 등장하지 않아야 함
        assert item.summary not in public_json, item.summary


# 공개 필드 집합 테스트
# PublicCase 모델과 실제 공개 JSON의 최상위 필드가 정해진 목록과 정확히 같은지 확인하는 함수
def test_public_case_fields_are_exact() -> None:
    # 모델 정의의 필드 집합 확인
    assert set(PublicCase.model_fields) == EXPECTED_PUBLIC_FIELDS
    # 실제 JSON 최상위 필드 집합 확인
    assert set(json.loads(build_public_json())) == EXPECTED_PUBLIC_FIELDS
