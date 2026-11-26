from typing import Any

import pytest
from agent_fakes import accuse_report, withhold_report

from app.agent.report_nodes import FORCED_WITHHOLD_REPORT
from app.schemas.report import FinalReport
from app.services.answer_key import load_answer_key
from app.services.case_repository import CaseRepository
from app.services.grading import grade_investigation

# 검증 대상 사건 ID (범인 S3, 결정적 증거 E1·E9·E19)
CASE_ID = "CASE-001"


# 최종 상태 생성
# 진행 상태·보고서·확보 증거 ID로 채점용 최종 상태를 만드는 함수
def make_state(
    status: str, report: FinalReport | None, collected_ids: list[str]
) -> dict[str, Any]:
    # 확보 증거 dict와 함께 상태 반환
    return {
        "case_id": CASE_ID,
        "status": status,
        "final_report": report,
        "collected_evidence": {
            evidence_id: {
                "id": evidence_id,
                "source_tool": "x",
                "summary": "s",
                "step": 1,
            }
            for evidence_id in collected_ids
        },
        "tool_call_count": 5,
        "validation_rejections": 0,
    }


# 판정별 채점 테스트
# 6가지 판정이 조건에 맞게 나오는지 확인하는 함수
@pytest.mark.parametrize(
    ("state", "verdict"),
    [
        (
            make_state(
                "completed",
                accuse_report("S3", ["E1", "E9", "E19"]),
                ["E1", "E9", "E19"],
            ),
            "full_success",
        ),
        (
            make_state(
                "completed", accuse_report("S3", ["E1", "E9"]), ["E1", "E9", "E19"]
            ),
            "partial_success",
        ),
        (
            make_state("completed", accuse_report("S3", ["E1"]), ["E1"]),
            "partial_success",
        ),
        (make_state("inconclusive", withhold_report(), ["E1"]), "appropriate_withhold"),
        (
            make_state("inconclusive", withhold_report(), ["E1", "E9", "E19"]),
            "inappropriate_withhold",
        ),
        (
            make_state("completed", accuse_report("S1", ["E1"]), ["E1", "E9", "E19"]),
            "failure",
        ),
        (make_state("failed", None, []), "error"),
        (make_state("completed", None, ["E1"]), "error"),
        (
            make_state(
                "failed", accuse_report("S3", ["E1", "E9", "E19"]), ["E1", "E9", "E19"]
            ),
            "error",
        ),
    ],
)
def test_verdicts(state: dict[str, Any], verdict: str) -> None:
    # 정답 키로 채점
    result = grade_investigation(state, load_answer_key(CASE_ID))
    assert result.verdict == verdict


# 강제 판단 보류 채점 테스트
# 강제 판단 보류 보고서도 보류로 판정되는지 확인하는 함수
def test_forced_withhold_is_withhold() -> None:
    # 결정적 증거 일부만 확보한 강제 보류
    state = make_state("inconclusive", FORCED_WITHHOLD_REPORT, ["E1"])
    assert grade_investigation(state, load_answer_key(CASE_ID)).verdict == (
        "appropriate_withhold"
    )
    # 결정적 증거를 모두 확보한 강제 보류
    state = make_state("inconclusive", FORCED_WITHHOLD_REPORT, ["E1", "E9", "E19"])
    assert grade_investigation(state, load_answer_key(CASE_ID)).verdict == (
        "inappropriate_withhold"
    )


# 채점 필드 테스트
# 채점 결과의 범인 이름·확보·인용 결정적 증거·경로 길이 등이 맞는지 확인하는 함수
def test_grading_fields() -> None:
    # 부분 성공 상태
    answer = load_answer_key(CASE_ID)
    case = CaseRepository().load_case(CASE_ID)
    state = make_state(
        "completed", accuse_report("S3", ["E1", "E9"]), ["E1", "E9", "E19"]
    )
    result = grade_investigation(state, answer, case)
    # 필드 확인
    assert result.culprit_id == "S3"
    assert result.culprit_name == "정민혁"
    assert result.accused_suspect_id == "S3"
    assert result.decisive_evidence_ids == ["E1", "E9", "E19"]
    assert result.collected_decisive_ids == ["E1", "E9", "E19"]
    assert result.cited_decisive_ids == ["E1", "E9"]
    assert result.tool_call_count == 5
    assert result.solution_path_length == 5
    assert result.grading_notes == answer.grading_notes
