import re
from pathlib import Path

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
