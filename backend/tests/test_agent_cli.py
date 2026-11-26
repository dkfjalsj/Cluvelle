from typing import Any

import pytest
from agent_fakes import ScriptedChatModel, accuse_report, finish_message
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage

from app.agent.cli import main
from app.config import Settings
from app.schemas.plan import InvestigationPlan, PlannedStep

# 테스트용 더미 키 (출력에 나오면 안 됨)
DUMMY_KEY = "dummy-cli-test-key-1234567890"


# 가짜 모델 생성 함수 만들기
# 설정을 무시하고 각본 모델을 돌려주는 모델 생성 함수를 만드는 함수
def fake_factory(responses: list[AIMessage]) -> Any:
    # 각본 모델 하나 생성 (보고서는 S3 지목)
    model = ScriptedChatModel(
        responses=responses, reports=[accuse_report("S3", ["E1", "E2"])]
    )

    # 가짜 모델 생성
    # 설정을 받아도 미리 만든 각본 모델을 반환하는 함수
    def factory(settings: Settings) -> BaseChatModel:
        # 미리 만든 각본 모델 반환
        return model

    # 생성 함수 반환
    return factory


# 기본 각본
# 현장 조사·교차 검증 뒤 결론을 내는 짧은 각본을 반환하는 함수
def basic_script() -> list[AIMessage]:
    # 현장 조사 1회, 심문 1회, 교차 검증 1회, 결론
    return [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "inspect_scene",
                    "args": {
                        "location_id": "L1",
                        "reason": "보관함 상태 확인",
                        "hypothesis": "테스트 가설",
                    },
                    "id": "c1",
                }
            ],
        ),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "inspect_scene",
                    "args": {
                        "location_id": "L3",
                        "reason": "창고 확인",
                        "hypothesis": "테스트 가설",
                    },
                    "id": "c2",
                }
            ],
        ),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "inspect_scene",
                    "args": {
                        "location_id": "L4",
                        "reason": "휴게실 확인",
                        "hypothesis": "테스트 가설",
                    },
                    "id": "c3",
                }
            ],
        ),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "cross_check_evidence",
                    "args": {
                        "evidence_ids": ["E1", "E2"],
                        "reason": "비교",
                        "hypothesis": "테스트 가설",
                    },
                    "id": "c4",
                }
            ],
        ),
        finish_message(),
    ]


# 정상 실행 테스트
# 가짜 모델로 실행하면 머리말·도구 블록·결론이 출력되고 종료 코드 0인지 확인하는 함수
def test_cli_runs_with_fake_model(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # 더미 키 환경변수 (실제 .env보다 우선)
    monkeypatch.setenv("GEMINI_API_KEY", DUMMY_KEY)
    # 가짜 모델로 실행
    exit_code = main(["CASE-001"], model_factory=fake_factory(basic_script()))
    output = capsys.readouterr().out
    # 종료 코드 확인
    assert exit_code == 0
    # 머리말 확인
    assert "사건: CASE-001" in output
    assert "방식: adaptive" in output
    assert "프롬프트 버전: adaptive-v3" in output
    assert "조사 예산: 10회" in output
    # 도구 블록 확인
    assert '[1/10] inspect_scene {"location_id": "L1"}' in output
    assert "  사유: 보관함 상태 확인" in output
    assert "  결과: 증거 E1" in output
    assert "  결과: 특이사항 없음" in output
    assert "  결과: 교차 검증 완료" in output
    # 종료 요약 확인
    assert "status: completed" in output
    assert "stop_reason: finished" in output
    assert "사용 횟수: 4/10" in output
    assert "report_status: accepted" in output
    assert "validation_rejections: 0" in output
    # 최종 보고서 블록 확인
    assert "=== 최종 보고서 ===" in output
    assert "결론: 지목" in output
    assert "용의자: S3" in output
    assert "근거 증거: E1, E2" in output
    assert "불일치:\n- 테스트 불일치" in output
    assert "미확인 사항:\n- 없음" in output
    assert "설명:\n테스트 설명" in output
    # 더미 키가 출력에 없어야 함
    assert DUMMY_KEY not in output


# 고정 계획형 실행 테스트
# --mode fixed로 실행하면 조사 계획·도구 블록·최종 보고서가 출력되는지 확인하는 함수
def test_cli_fixed_mode(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # 더미 키 환경변수
    monkeypatch.setenv("GEMINI_API_KEY", DUMMY_KEY)
    # 2단계 계획과 지목 보고서 각본
    plan = InvestigationPlan(
        steps=[
            PlannedStep(tool="inspect_scene", location_id="L1", reason="보관함 확인"),
            PlannedStep(tool="inspect_scene", location_id="L3", reason="창고 확인"),
        ],
        rationale="현장부터 확인한다.",
    )
    model = ScriptedChatModel(plans=[plan], reports=[accuse_report("S3", ["E1", "E2"])])

    # 가짜 모델 생성
    # 설정을 받아도 미리 만든 각본 모델을 반환하는 함수
    def factory(settings: Settings) -> BaseChatModel:
        # 미리 만든 각본 모델 반환
        return model

    # 고정 계획형으로 실행
    exit_code = main(["CASE-001", "--mode", "fixed"], model_factory=factory)
    output = capsys.readouterr().out
    # 종료 코드와 머리말 확인
    assert exit_code == 0
    assert "방식: fixed" in output
    assert "프롬프트 버전: fixed-v1" in output
    # 조사 계획 블록 확인
    assert "=== 조사 계획 ===" in output
    assert '1. inspect_scene {"location_id": "L1"}' in output
    assert "   사유: 보관함 확인" in output
    assert "계획 의도: 현장부터 확인한다." in output
    # 도구 블록과 최종 보고서 확인
    assert '[2/10] inspect_scene {"location_id": "L3"}' in output
    assert "=== 최종 보고서 ===" in output
    assert "report_status: accepted" in output
    # 더미 키가 출력에 없어야 함
    assert DUMMY_KEY not in output


# 잘못된 방식 테스트
# --mode 값이 adaptive·fixed가 아니면 종료 코드 2인지 확인하는 함수
@pytest.mark.parametrize(
    "argv", [["CASE-001", "--mode", "random"], ["CASE-001", "--mode"]]
)
def test_cli_invalid_mode(argv: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    # 잘못된 방식으로 실행
    exit_code = main(argv, model_factory=fake_factory(basic_script()))
    output = capsys.readouterr().out
    # 종료 코드와 사용법 안내 확인
    assert exit_code == 2
    assert "사용법:" in output


# 키 없음 테스트
# API 키가 비어 있으면 키 안내 문구를 출력하고 종료 코드 1인지 확인하는 함수
def test_cli_missing_key(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # 빈 키 환경변수 (실제 .env보다 우선)
    monkeypatch.setenv("GEMINI_API_KEY", "")
    # 기본 모델 생성 함수로 실행
    exit_code = main(["CASE-001"])
    output = capsys.readouterr().out
    # 종료 코드와 안내 문구 확인
    assert exit_code == 1
    assert "GEMINI_API_KEY가 설정되지 않았습니다" in output


# 잘못된 사건 ID 테스트
# 형식이 틀리거나 없는 사건 ID면 종료 코드 2인지 확인하는 함수
@pytest.mark.parametrize("case_id", ["case-1", "CASE-998"])
def test_cli_bad_case_id(
    case_id: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # 더미 키 환경변수
    monkeypatch.setenv("GEMINI_API_KEY", DUMMY_KEY)
    # 잘못된 ID로 실행
    exit_code = main([case_id], model_factory=fake_factory(basic_script()))
    output = capsys.readouterr().out
    # 종료 코드와 한 줄 오류 확인
    assert exit_code == 2
    assert output.strip().startswith("오류:")
    assert len(output.strip().splitlines()) == 1
