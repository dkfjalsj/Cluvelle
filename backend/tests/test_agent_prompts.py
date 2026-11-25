import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.agent.prompts import build_case_brief
from app.agent.tool_specs import TOOL_INPUT_MODELS, get_llm_tools
from app.services.case_repository import CaseRepository

# 에이전트 소스 폴더
AGENT_DIR = Path(__file__).resolve().parents[1] / "app" / "agent"
# 도구 이름 집합
TOOL_NAMES = {
    "inspect_scene",
    "interview_suspect",
    "check_cctv",
    "verify_alibi",
    "cross_check_evidence",
}


# CASE-001 브리핑 생성
# 기본 저장소의 CASE-001 공개 정보로 브리핑 문자열을 만들어 반환하는 함수
def build_case_001_brief() -> str:
    # 공개 정보로 브리핑 생성
    return build_case_brief(CaseRepository().get_public_case("CASE-001"))


# 브리핑 공개 정보 테스트
# 브리핑에 모든 공개 ID·카메라 시간대·예산·off_site 안내가 있는지 확인하는 함수
def test_brief_contains_public_info() -> None:
    # 브리핑 생성
    brief = build_case_001_brief()
    # 모든 공개 ID 확인
    public_ids = (
        [f"S{number}" for number in range(1, 4)]
        + [f"L{number}" for number in range(1, 7)]
        + [f"C{number}" for number in range(1, 4)]
        + [f"T{number}" for number in range(1, 5)]
    )
    for public_id in public_ids:
        assert public_id in brief, public_id
    # 카메라 시간대 확인
    for window in ("20:00-21:00", "21:00-22:00", "22:00-23:00"):
        assert window in brief
    # 예산과 off_site 안내 확인
    assert "조사 예산: 10회" in brief
    assert '사건 현장 밖 장소는 "연구동 밖"로 표기된다.' in brief
    # 설명이 있는 장소·카메라는 "이름 - 설명"으로 표기
    assert "- L1 실험실 - 보관함 있음" in brief
    assert (
        "- C3 주차장 비상계단 출입구 카메라 - 출입구 바로 위 근접 설치 (조회 가능 시간대:"
        in brief
    )
    # 설명이 없는 장소는 이름만
    assert "- L2 3층 복도\n" in brief


# 브리핑 정답 미노출 테스트
# 브리핑에 증거 ID·자산 태그·증거 요약 문장이 없는지 확인하는 함수
def test_brief_hides_evidence() -> None:
    # 브리핑과 원본 사건
    brief = build_case_001_brief()
    case = CaseRepository().load_case("CASE-001")
    # 증거 ID E1~E22가 단어 단위로 없어야 함
    for number in range(1, 23):
        assert re.search(rf"\bE{number}\b", brief) is None, f"E{number}"
    # 자산 태그가 없어야 함
    assert "RL-0417" not in brief
    # 증거 요약 문장이 없어야 함
    for item in case.evidence:
        assert item.summary not in brief, item.id


# LLM 도구 명세 테스트
# 도구 이름이 5개와 같고 각 입력 스키마에 reason이 필수이며 case 필드가 없는지 확인하는 함수
def test_llm_tools_schema() -> None:
    # 도구 명세 목록
    tools = get_llm_tools()
    # 이름 집합 확인
    names = {tool["function"]["name"] for tool in tools}
    assert names == TOOL_NAMES
    assert set(TOOL_INPUT_MODELS) == TOOL_NAMES
    # 도구마다 입력 스키마 확인
    for tool in tools:
        parameters = tool["function"]["parameters"]
        # reason 필수
        assert "reason" in parameters["required"]
        # case 필드 없음
        assert "case" not in parameters["properties"]
        # 설명은 한국어 문장
        assert tool["function"]["description"]


# 키 이름 수집
# 중첩된 dict·list를 돌며 등장하는 모든 키 이름을 모아 반환하는 함수
def collect_keys(value: object) -> set[str]:
    # 수집한 키 집합
    keys: set[str] = set()
    # dict면 키를 모으고 값도 재귀 탐색
    if isinstance(value, dict):
        for key, item in value.items():
            keys.add(str(key))
            keys |= collect_keys(item)
    # list면 각 항목을 재귀 탐색
    elif isinstance(value, list):
        for item in value:
            keys |= collect_keys(item)
    # 수집 결과 반환
    return keys


# additionalProperties 제거 테스트
# LLM 도구 스키마 어디에도 additionalProperties가 없는지 확인하는 함수
def test_llm_tools_have_no_additional_properties() -> None:
    # 모든 도구 명세의 키 수집
    keys = collect_keys(get_llm_tools())
    # additionalProperties가 없어야 함
    assert "additionalProperties" not in keys


# 입력 모델 엄격 검증 유지 테스트
# 입력 모델이 여전히 알 수 없는 필드를 거부하는지 확인하는 함수
def test_input_models_still_forbid_extra() -> None:
    # 모델마다 올바른 인자를 만든 뒤 알 수 없는 필드만 더해 검증
    for model in TOOL_INPUT_MODELS.values():
        # 필수 필드를 채운 올바른 인자 (목록 필드는 증거 ID 목록)
        valid_args: dict[str, object] = {
            name: ["E1", "E2"] if name == "evidence_ids" else "값"
            for name in model.model_fields
        }
        # 올바른 인자는 통과해야 함
        model.model_validate(valid_args)
        # 알 수 없는 필드가 더해지면 거부해야 함
        with pytest.raises(ValidationError):
            model.model_validate({**valid_args, "unknown_field": "값"})


# 정답 모듈 미참조 테스트
# app/agent 아래 모든 소스가 정답 모듈·폴더를 import하지 않는지 확인하는 함수
def test_agent_does_not_import_answers() -> None:
    # import 줄 중 answer가 들어간 줄을 찾는 정규식
    pattern = re.compile(r"^\s*(from|import)\s+[^\n]*answer", re.MULTILINE)
    # 에이전트 폴더의 모든 파이썬 파일 검사
    sources = list(AGENT_DIR.rglob("*.py"))
    assert sources
    for path in sources:
        source = path.read_text(encoding="utf-8")
        # answer 관련 import가 없어야 함
        assert pattern.search(source) is None, path.name
