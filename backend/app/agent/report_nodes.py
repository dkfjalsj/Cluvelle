from collections.abc import Callable
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph import END

from app.agent.execution import describe_error
from app.agent.prompts import build_report_feedback, build_report_request
from app.agent.state import CollectedEvidence, InvestigationState, ReportError
from app.schemas.case import CaseFile
from app.schemas.report import FinalReport

# 노드 이름
REPORT_NODE = "report"
REPORT_VALIDATOR_NODE = "report_validator"

# 보고서 최대 실패 횟수 (형식 오류 포함)
MAX_REPORT_FAILURES = 2

# 노드 함수 형식 (상태 → 변경분)
NodeFunction = Callable[[InvestigationState], dict[str, Any]]


# 강제 판단 보류 보고서 생성
# 보고서가 2회 검증에 실패했을 때 쓰는 고정 판단 보류 보고서를 만드는 함수
def build_forced_withhold_report() -> FinalReport:
    # 고정 내용의 판단 보류 보고서 반환
    return FinalReport(
        verdict="withhold",
        suspect_id=None,
        cited_evidence_ids=[],
        contradictions=[],
        unverified=["보고서 검증 실패로 결론을 확정하지 못했습니다."],
        explanation="최종 보고서가 2회 검증에 실패해 판단을 보류합니다.",
    )


# 강제 판단 보류 보고서
FORCED_WITHHOLD_REPORT = build_forced_withhold_report()


# 보고서 노드 생성
# LLM과 사건을 받아 최종 보고서를 구조화 출력으로 받아 검증 대기 보고서로 저장하는 노드를 만드는 함수
def make_report_node(llm: BaseChatModel, case: CaseFile) -> NodeFunction:
    # 최종 보고서 구조화 출력 LLM (원문·파싱 오류도 함께 받음)
    report_llm = llm.with_structured_output(FinalReport, include_raw=True)
    # 용의자 ID 목록
    suspect_ids = [suspect.id for suspect in case.suspects]

    # 보고서 노드
    # 확보 증거 안에서 최종 보고서를 받아 pending_report에 저장하는 함수
    def report(state: InvestigationState) -> dict[str, Any]:
        # 이번 시도 번호 (이전 실패 시도 수 + 1)
        attempt = failed_attempts(state["report_errors"]) + 1
        # 이번에 추가할 요청 메시지 (첫 시도는 보고서 요청, 재시도는 피드백)
        if attempt == 1:
            request = build_report_request(
                list(state["collected_evidence"]), suspect_ids
            )
        else:
            request = build_report_feedback(
                [
                    item["detail"]
                    for item in state["report_errors"]
                    if item["attempt"] == attempt - 1
                ]
            )
        new_messages: list[BaseMessage] = [HumanMessage(content=request)]

        # 구조화 출력 호출 (네트워크·API 오류면 실패 상태로 종료)
        try:
            output = report_llm.invoke([*state["messages"], *new_messages])
        except Exception as error:  # noqa: BLE001
            # 보고서 단계 오류는 실패 처리 (수사 종료 사유는 유지)
            return {
                "messages": new_messages,
                "status": "failed",
                "error": describe_error(error),
            }

        # 원문·파싱 결과·파싱 오류 꺼내기
        raw, parsed, parsing_error = unpack_structured_output(output)
        # 형식 오류면 parse 오류 기록 (인용 오류 횟수는 늘리지 않음)
        if parsing_error is not None or not isinstance(parsed, FinalReport):
            detail = f"보고서 형식 오류: {parsing_error or '구조화 결과 없음'}"
            new_messages.append(AIMessage(content=raw_text(raw)))
            return {
                "messages": new_messages,
                "pending_report": None,
                "report_errors": [
                    *state["report_errors"],
                    ReportError(attempt=attempt, kind="parse", detail=detail[:500]),
                ],
            }
        # 정상 파싱이면 보고서 JSON을 대화에 남기고 검증 대기 보고서로 저장
        new_messages.append(AIMessage(content=parsed.model_dump_json()))
        return {"messages": new_messages, "pending_report": parsed}

    # 노드 반환
    return report


# 보고서 검증 노드 생성
# 사건을 받아 검증 대기 보고서를 사건 데이터·확보 증거와 대조하는 노드를 만드는 함수
def make_report_validator(case: CaseFile) -> NodeFunction:
    # 보고서 검증 노드
    # 보고서의 용의자·인용 증거를 대조해 통과·재작성·강제 판단 보류를 정하는 함수
    def report_validator(state: InvestigationState) -> dict[str, Any]:
        # 검증 대기 보고서와 오류 기록
        candidate = state["pending_report"]
        report_errors = list(state["report_errors"])
        rejections = state["validation_rejections"]
        # 형식 오류가 아니면 사건 데이터와 대조
        if candidate is not None:
            attempt = failed_attempts(report_errors) + 1
            problems = validate_report(candidate, case, state["collected_evidence"])
            # 문제가 없으면 통과: 최종 보고서로 옮기고 대기 보고서 비움
            if not problems:
                return {
                    "final_report": candidate,
                    "pending_report": None,
                    "report_status": "accepted",
                    "status": (
                        "completed" if candidate.verdict == "accuse" else "inconclusive"
                    ),
                }
            # 문제가 있으면 거절 횟수 1 증가 후 오류 기록
            rejections += 1
            report_errors.extend(
                ReportError(attempt=attempt, kind=kind, detail=detail)
                for kind, detail in problems
            )
        # 누적 실패가 한도에 이르면 강제 판단 보류
        if failed_attempts(report_errors) >= MAX_REPORT_FAILURES:
            return {
                "final_report": build_forced_withhold_report(),
                "pending_report": None,
                "report_status": "forced_withhold",
                "status": "inconclusive",
                "validation_rejections": rejections,
                "report_errors": report_errors,
            }
        # 아니면 재작성을 위해 대기 보고서를 비우고 기록 갱신
        return {
            "pending_report": None,
            "validation_rejections": rejections,
            "report_errors": report_errors,
        }

    # 노드 반환
    return report_validator


# 보고서 다음 경로
# 보고서 단계에서 실패했으면 종료, 아니면 검증으로 보내는 함수
def route_after_report(state: InvestigationState) -> str:
    # API 오류 등으로 실패면 종료
    if state["status"] == "failed":
        return END
    # 서버 검증으로 이동
    return REPORT_VALIDATOR_NODE


# 검증 다음 경로
# 보고서 처리가 끝났으면 종료, 아니면 보고서 재작성으로 보내는 함수
def route_after_validator(state: InvestigationState) -> str:
    # 통과 또는 강제 판단 보류면 종료
    if state["report_status"] is not None:
        return END
    # 재작성
    return REPORT_NODE


# 보고서 검증
# 보고서의 용의자·인용 증거를 사건과 확보 증거에 대조해 (오류 종류, 내용) 목록을 반환하는 함수
def validate_report(
    candidate: FinalReport,
    case: CaseFile,
    collected: dict[str, CollectedEvidence],
) -> list[tuple[Any, str]]:
    # 발견한 문제 목록
    problems: list[tuple[Any, str]] = []
    # 지목한 용의자가 사건 용의자가 아니면 오류
    suspect_ids = {suspect.id for suspect in case.suspects}
    if candidate.verdict == "accuse" and candidate.suspect_id not in suspect_ids:
        problems.append(
            (
                "invalid_suspect",
                f"사건 용의자가 아닌 ID를 지목했습니다: {candidate.suspect_id}",
            )
        )
    # 확보하지 않은 증거를 인용했으면 오류
    uncollected = [
        evidence_id
        for evidence_id in candidate.cited_evidence_ids
        if evidence_id not in collected
    ]
    if uncollected:
        problems.append(
            (
                "uncollected_evidence",
                f"확보하지 않은 증거를 인용했습니다: {', '.join(uncollected)}",
            )
        )
    # 지목인데 근거 증거가 없으면 오류
    if candidate.verdict == "accuse" and not candidate.cited_evidence_ids:
        problems.append(
            ("missing_evidence", "용의자를 지목했지만 근거 증거 ID가 없습니다.")
        )
    # 문제 목록 반환
    return problems


# 실패 시도 수
# 보고서 오류 기록에서 실패한 시도 번호의 개수를 세는 함수
def failed_attempts(report_errors: list[ReportError]) -> int:
    # 서로 다른 시도 번호 개수 반환
    return len({item["attempt"] for item in report_errors})


# 구조화 출력 풀기
# include_raw 구조화 출력에서 원문 메시지·파싱 결과·파싱 오류를 꺼내는 함수
def unpack_structured_output(output: Any) -> tuple[Any, Any, Any]:
    # 원문·파싱 결과·오류를 담은 dict면 각각 꺼내기
    if isinstance(output, dict):
        return output.get("raw"), output.get("parsed"), output.get("parsing_error")
    # 그 외 형태면 파싱 결과만 있는 것으로 처리
    return None, output, None


# 원문 텍스트
# 구조화 출력 원문 메시지에서 대화에 남길 텍스트를 꺼내는 함수
def raw_text(raw: Any) -> str:
    # 원문 메시지의 텍스트 (비어 있으면 대체 문구)
    text = raw.text if isinstance(raw, AIMessage) else ""
    return text or "(보고서 형식 오류)"
