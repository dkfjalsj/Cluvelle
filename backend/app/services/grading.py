"""수사 채점.

최종 상태를 정답 키와 비교하는 결정적 채점 함수다. API와 평가 스크립트가 함께 쓴다.
"""

from collections.abc import Mapping
from typing import Any

from app.schemas.answer import AnswerKey
from app.schemas.api import GradingResult, GradingVerdict
from app.schemas.case import CaseFile
from app.schemas.report import FinalReport
from app.services.answer_key import load_answer_key
from app.services.case_repository import CaseRepository


# 수사 채점
# 최종 상태와 정답 키(이름 표기용 사건 포함)를 받아 판정과 근거 수치를 반환하는 함수
def grade_investigation(
    state: Mapping[str, Any],
    answer: AnswerKey,
    case: CaseFile | None = None,
) -> GradingResult:
    # 사건이 없으면 상태의 사건 ID로 로드 (범인 이름 표기용)
    case = case or CaseRepository().load_case(answer.case_id)
    # 범인 이름
    names = {suspect.id: suspect.name for suspect in case.suspects}
    # 최종 보고서와 확보 증거
    report = state.get("final_report")
    collected = state.get("collected_evidence") or {}
    # 결정적 증거 중 확보·인용한 것
    decisive = list(answer.decisive_evidence_ids)
    collected_decisive = [item for item in decisive if item in collected]
    cited = report.cited_evidence_ids if isinstance(report, FinalReport) else []
    cited_decisive = [item for item in decisive if item in cited]
    # 판정
    verdict = _decide_verdict(
        state.get("status"),
        report if isinstance(report, FinalReport) else None,
        answer.culprit_id,
        all_collected=len(collected_decisive) == len(decisive),
        all_cited=len(cited_decisive) == len(decisive),
    )
    # 지목한 용의자 (지목 보고서일 때만)
    accused = (
        report.suspect_id
        if isinstance(report, FinalReport) and report.verdict == "accuse"
        else None
    )
    # 채점 결과 반환
    return GradingResult(
        verdict=verdict,
        culprit_id=answer.culprit_id,
        culprit_name=names.get(answer.culprit_id, answer.culprit_id),
        accused_suspect_id=accused,
        decisive_evidence_ids=decisive,
        collected_decisive_ids=collected_decisive,
        cited_decisive_ids=cited_decisive,
        tool_call_count=int(state.get("tool_call_count") or 0),
        validation_rejections=int(state.get("validation_rejections") or 0),
        solution_path_length=len(answer.solution_path),
        grading_notes=answer.grading_notes,
    )


# 최종 상태 채점
# 상태의 사건 ID로 정답 키와 사건을 불러와 채점 결과를 반환하는 함수
def grade_final_state(state: Mapping[str, Any]) -> GradingResult:
    # 사건 ID로 정답 키와 사건 로드
    case_id = str(state["case_id"])
    answer = load_answer_key(case_id)
    case = CaseRepository().load_case(case_id)
    # 채점
    return grade_investigation(state, answer, case)


# 판정 결정
# 진행 상태·보고서·범인과 결정적 증거 확보·인용 여부로 6가지 판정 중 하나를 고르는 함수
def _decide_verdict(
    status: Any,
    report: FinalReport | None,
    culprit_id: str,
    *,
    all_collected: bool,
    all_cited: bool,
) -> GradingVerdict:
    # 실패 상태이거나 보고서가 없으면 오류
    if status == "failed" or report is None:
        return "error"
    # 판단 보류(강제 보류 포함)는 결정적 증거 확보 여부로 적절성 판정
    if report.verdict == "withhold":
        return "inappropriate_withhold" if all_collected else "appropriate_withhold"
    # 범인이 아닌 사람을 지목하면 실패
    if report.suspect_id != culprit_id:
        return "failure"
    # 범인 지목 + 결정적 증거 모두 확보·인용이면 완전 성공, 아니면 부분 성공
    if all_collected and all_cited:
        return "full_success"
    return "partial_success"
