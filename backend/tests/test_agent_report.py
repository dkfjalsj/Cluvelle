from typing import Any

from agent_fakes import (
    ScriptedChatModel,
    accuse_report,
    finish_message,
    tool_call_message,
    withhold_report,
)
from langchain_core.messages import AIMessage, HumanMessage

from app.agent.graph import FORCED_WITHHOLD_REPORT
from app.agent.runner import run_investigation
from app.agent.state import InvestigationState
from app.schemas.report import FinalReport

# 검증 대상 사건 ID
CASE_ID = "CASE-001"
# 정답 경로 도구 호출
SOLUTION_STEPS = [
    ("inspect_scene", {"location_id": "L1"}),
    ("inspect_scene", {"location_id": "L3"}),
    ("check_cctv", {"camera_id": "C3", "time_window": "22:00-23:00"}),
    ("interview_suspect", {"suspect_id": "S3", "topic_id": "T1"}),
    ("cross_check_evidence", {"evidence_ids": ["E9", "E19"]}),
]
# 형식 오류를 일으키는 보고서 값 (필수 필드 누락)
MALFORMED_REPORT: dict[str, Any] = {"verdict": "accuse"}


# 정답 경로 응답 생성
# 정답 경로 5회 조사 뒤 수사 종료하는 응답 목록을 만드는 함수
def solution_responses() -> list[AIMessage]:
    # 정답 경로 호출과 수사 종료
    responses = [
        tool_call_message(name, {**args, "reason": "조사"}, f"c{index}")
        for index, (name, args) in enumerate(SOLUTION_STEPS, start=1)
    ]
    return [*responses, finish_message()]


# 보고서 각본 실행
# 정답 경로 조사 뒤 주어진 보고서 각본으로 수사를 실행해 상태와 모델을 반환하는 함수
def run_with_reports(
    reports: list[Any],
) -> tuple[InvestigationState, ScriptedChatModel]:
    # 정답 경로 응답과 보고서 각본으로 모델 생성
    model = ScriptedChatModel(responses=solution_responses(), reports=reports)
    # 수사 실행
    state = run_investigation(CASE_ID, model)
    # 상태와 모델 반환
    return state, model


# 지목 보고서 통과 테스트
# 정답 경로 뒤 S3 지목 보고서가 통과해 완료 상태가 되는지 확인하는 함수
def test_accuse_report_accepted() -> None:
    # 지목 보고서
    state, _ = run_with_reports([accuse_report("S3", ["E1", "E9", "E19"])])
    # 완료·통과 확인
    assert state["status"] == "completed"
    assert state["report_status"] == "accepted"
    assert state["validation_rejections"] == 0
    assert state["final_report"] is not None
    assert state["final_report"].suspect_id == "S3"


# 판단 보류 보고서 테스트
# 판단 보류 보고서가 통과하면 판단 보류 상태가 되는지 확인하는 함수
def test_withhold_report_accepted() -> None:
    # 판단 보류 보고서
    state, _ = run_with_reports([withhold_report(["E1"])])
    # 판단 보류·통과 확인
    assert state["status"] == "inconclusive"
    assert state["report_status"] == "accepted"


# 1차 거절 후 통과 테스트
# 미확보 증거를 인용한 첫 보고서가 거절되고 두 번째 보고서가 통과하는지 확인하는 함수
def test_uncollected_then_accepted() -> None:
    # 1차 E22(미확보) 인용, 2차 정상
    state, model = run_with_reports(
        [
            accuse_report("S3", ["E19", "E22"]),
            accuse_report("S3", ["E1", "E9", "E19"]),
        ]
    )
    # 통과와 거절 집계 확인
    assert state["report_status"] == "accepted"
    assert state["validation_rejections"] == 1
    assert len(state["report_errors"]) == 1
    assert state["report_errors"][0]["kind"] == "uncollected_evidence"
    assert "E22" in state["report_errors"][0]["detail"]
    # 두 번째 요청에 피드백 메시지가 들어감
    second_request = model.report_received[1]
    assert isinstance(second_request[-1], HumanMessage)
    assert str(second_request[-1].content).startswith("보고서가 검증에 실패했다.")
    assert "E22" in str(second_request[-1].content)


# 2회 거절 강제 보류 테스트
# 미확보 증거 인용이 2회 연속이면 강제 판단 보류 보고서로 끝나는지 확인하는 함수
def test_two_rejections_force_withhold() -> None:
    # 두 번 모두 E22 인용
    state, _ = run_with_reports(
        [accuse_report("S3", ["E22"]), accuse_report("S3", ["E22"])]
    )
    # 강제 판단 보류 확인
    assert state["report_status"] == "forced_withhold"
    assert state["validation_rejections"] == 2
    assert state["status"] == "inconclusive"
    # 강제 보고서 내용이 명세와 같음
    assert state["final_report"] == FinalReport(
        verdict="withhold",
        suspect_id=None,
        cited_evidence_ids=[],
        contradictions=[],
        unverified=["보고서 검증 실패로 결론을 확정하지 못했습니다."],
        explanation="최종 보고서가 2회 검증에 실패해 판단을 보류합니다.",
    )
    assert state["final_report"] == FORCED_WITHHOLD_REPORT


# 없는 용의자 지목 테스트
# 사건에 없는 용의자를 지목하면 invalid_suspect로 거절되는지 확인하는 함수
def test_invalid_suspect_rejected() -> None:
    # 1차 S9 지목, 2차 정상
    state, _ = run_with_reports(
        [accuse_report("S9", ["E1"]), accuse_report("S3", ["E1", "E9", "E19"])]
    )
    # 거절 종류 확인
    assert state["report_errors"][0]["kind"] == "invalid_suspect"
    assert state["validation_rejections"] == 1
    assert state["report_status"] == "accepted"


# 근거 없는 지목 테스트
# 지목인데 근거 증거가 없으면 missing_evidence로 거절되는지 확인하는 함수
def test_missing_evidence_rejected() -> None:
    # 1차 근거 없는 지목, 2차 정상
    state, _ = run_with_reports(
        [accuse_report("S3", []), accuse_report("S3", ["E1", "E9", "E19"])]
    )
    # 거절 종류 확인
    assert state["report_errors"][0]["kind"] == "missing_evidence"
    assert state["validation_rejections"] == 1


# 형식 오류 2회 테스트
# 보고서 형식 오류가 2회면 강제 판단 보류이고 인용 오류 횟수는 늘지 않는지 확인하는 함수
def test_two_parse_errors_force_withhold() -> None:
    # 형식 오류 2회
    state, _ = run_with_reports([MALFORMED_REPORT, MALFORMED_REPORT])
    # 강제 보류, 인용 오류 0, parse 오류 2건
    assert state["report_status"] == "forced_withhold"
    assert state["validation_rejections"] == 0
    assert [item["kind"] for item in state["report_errors"]] == ["parse", "parse"]


# 보고서 API 오류 테스트
# 보고서 요청 중 예외가 나면 실패 상태로 끝나는지 확인하는 함수
def test_report_api_error_fails() -> None:
    # 보고서 요청에서 예외
    state, _ = run_with_reports([RuntimeError("보고서 요청 실패")])
    # 실패 상태와 오류 기록, 수사 종료 사유는 유지
    assert state["status"] == "failed"
    assert state["stop_reason"] == "finished"
    assert state["error"] is not None
    assert "RuntimeError" in state["error"]
    assert state["report_status"] is None


# 보고서 요청 메시지 테스트
# 보고서 요청 문구에 확보한 증거 ID만 정확히 들어가는지 확인하는 함수
def test_report_request_lists_collected_ids() -> None:
    # 정답 경로 뒤 지목 보고서
    state, model = run_with_reports([accuse_report("S3", ["E1", "E9", "E19"])])
    # 첫 보고서 요청 메시지
    request = str(model.report_received[0][-1].content)
    # 확보 증거 목록 줄 찾기
    prefix = "- 인용할 수 있는 증거는 지금까지 확보한 증거뿐이다: "
    lines = [line for line in request.splitlines() if line.startswith(prefix)]
    assert len(lines) == 1
    # 줄에 적힌 ID 집합이 확보 증거 집합과 정확히 같음 (미확보 ID 없음)
    listed = lines[0].removeprefix(prefix).split(", ")
    assert set(listed) == set(state["collected_evidence"])
    assert len(listed) == len(state["collected_evidence"])
    # 용의자 목록 포함
    assert "- 지목할 수 있는 용의자: S1, S2, S3" in request
