import json
import sys
import time
from collections.abc import Callable

from langchain_core.language_models import BaseChatModel

from app.agent.llm import MissingApiKeyError, create_chat_model
from app.agent.prompts import FIXED_PROMPT_VERSION, PROMPT_VERSION
from app.agent.runner import InvestigationMode, run_investigation
from app.agent.state import HistoryEntry, InvestigationState
from app.config import Settings
from app.schemas.plan import InvestigationPlan
from app.schemas.report import FinalReport
from app.services.case_repository import (
    CaseNotFoundError,
    CaseRepository,
    InvalidCaseIdError,
)

# 결론 종류 표기
VERDICT_LABELS = {"accuse": "지목", "withhold": "판단 보류"}
# 방식별 프롬프트 버전
PROMPT_VERSIONS: dict[str, str] = {
    "adaptive": PROMPT_VERSION,
    "fixed": FIXED_PROMPT_VERSION,
}
# 사용법 안내
USAGE = "사용법: uv run python -m app.agent.cli CASE-001 [--mode adaptive|fixed]"

# 모델 생성 함수 형식 (설정 → 채팅 모델)
ModelFactory = Callable[[Settings], BaseChatModel]

# 종료 코드
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_BAD_CASE = 2


# 실행 진입점
# 사건 ID를 받아 실제 모델로 수사를 실행하고 결과를 출력한 뒤 종료 코드를 반환하는 함수
def main(
    argv: list[str] | None = None,
    model_factory: ModelFactory = create_chat_model,
) -> int:
    # 명령줄 인자 (없으면 실제 명령줄 사용)
    args = sys.argv[1:] if argv is None else argv
    # 사건 ID와 실행 방식 해석 (잘못되면 사용법 안내 후 종료)
    parsed = parse_args(args)
    if parsed is None:
        print(USAGE)
        return EXIT_BAD_CASE
    case_id, mode = parsed

    # 사건 ID 확인 (형식 오류·없음이면 한 줄 오류 후 종료)
    repository = CaseRepository()
    try:
        case = repository.load_case(case_id)
    except (InvalidCaseIdError, CaseNotFoundError) as error:
        print(f"오류: {error}")
        return EXIT_BAD_CASE

    # 설정 로드 후 모델 생성 (키가 없으면 안내 후 종료)
    settings = Settings()
    try:
        llm = model_factory(settings)
    except MissingApiKeyError as error:
        print(f"오류: {error}")
        return EXIT_FAILED

    # 머리말 출력 (방식과 해당 프롬프트 버전)
    print(f"사건: {case.case_id}")
    print(f"방식: {mode}")
    print(f"모델: {settings.gemini_model}")
    print(f"프롬프트 버전: {PROMPT_VERSIONS[mode]}")
    print(f"조사 예산: {case.tool_budget}회")
    print()

    # 수사 실행과 시간 측정
    started = time.perf_counter()
    state = run_investigation(case_id, llm, mode=mode, repository=repository)
    elapsed = time.perf_counter() - started

    # 고정 계획형이면 조사 계획 먼저 출력
    plan = state["plan"]
    if plan is not None:
        print(format_plan(plan))
        print()
    # 결과 출력
    print_report(state, case.tool_budget, elapsed)
    # 실패면 1, 그 외 0
    return EXIT_FAILED if state["status"] == "failed" else EXIT_OK


# 명령줄 인자 해석
# 사건 ID 하나와 선택 옵션 --mode를 읽어 (사건 ID, 방식)을 반환하는 함수 (잘못되면 None)
def parse_args(args: list[str]) -> tuple[str, InvestigationMode] | None:
    # 위치 인자와 방식 기본값
    positional: list[str] = []
    mode_value = "adaptive"
    index = 0
    # 인자를 앞에서부터 해석
    while index < len(args):
        token = args[index]
        if token == "--mode":
            # 다음 인자가 방식 값
            if index + 1 >= len(args):
                return None
            mode_value = args[index + 1]
            index += 2
            continue
        if token.startswith("--mode="):
            # 등호 뒤가 방식 값
            mode_value = token.split("=", 1)[1]
        elif token.startswith("--"):
            # 알 수 없는 옵션
            return None
        else:
            # 위치 인자 (사건 ID)
            positional.append(token)
        index += 1
    # 사건 ID가 정확히 하나이고 방식 값이 올바라야 함
    if len(positional) != 1:
        return None
    if mode_value == "adaptive":
        return positional[0], "adaptive"
    if mode_value == "fixed":
        return positional[0], "fixed"
    return None


# 조사 계획 블록 생성
# 고정 계획형의 계획 단계(번호·도구·인자·이유)와 전체 의도를 여러 줄 문자열로 만드는 함수
def format_plan(plan: InvestigationPlan) -> str:
    # 제목 줄
    lines = ["=== 조사 계획 ==="]
    # 단계마다 한 줄 + 이유 한 줄
    for number, step in enumerate(plan.steps, start=1):
        step_args = step.model_dump(exclude={"tool", "reason"}, exclude_none=True)
        args_text = json.dumps(step_args, ensure_ascii=False)
        lines.append(f"{number}. {step.tool} {args_text}")
        lines.append(f"   사유: {step.reason}")
    # 전체 의도
    lines.append(f"계획 의도: {plan.rationale}")
    # 줄바꿈으로 합쳐 반환
    return "\n".join(lines)


# 결과 출력
# 도구 호출 기록, 종료 상태, 결론·오류를 정해진 형식으로 출력하는 함수
def print_report(state: InvestigationState, budget: int, elapsed: float) -> None:
    # 도구 호출마다 한 블록 출력
    for entry in state["investigation_history"]:
        print(format_history_entry(entry, budget))
    # 종료 상태 요약
    print()
    print(f"status: {state['status']}")
    print(f"stop_reason: {state['stop_reason']}")
    print(f"사용 횟수: {state['tool_call_count']}/{budget}")
    collected = ", ".join(state["collected_evidence"]) or "없음"
    print(f"확보 증거: {collected}")
    print(f"report_status: {state['report_status']}")
    print(f"validation_rejections: {state['validation_rejections']}")
    print(f"걸린 시간: {elapsed:.1f}초")
    # 최종 보고서가 있으면 출력
    final_report = state["final_report"]
    if final_report is not None:
        print()
        print("=== 최종 보고서 ===")
        print(format_final_report(final_report))
    # 오류가 있으면 출력
    if state["error"]:
        print()
        print("=== 오류 ===")
        print(state["error"])


# 최종 보고서 블록 생성
# 보고서의 결론·용의자·근거 증거·불일치·미확인 사항·설명을 여러 줄 문자열로 만드는 함수
def format_final_report(final_report: FinalReport) -> str:
    # 결론 표기 (지목/판단 보류)
    verdict = VERDICT_LABELS[final_report.verdict]
    # 목록 항목을 줄로 만드는 보조 표현
    contradictions = _bullet_lines(final_report.contradictions)
    unverified = _bullet_lines(final_report.unverified)
    # 블록 조합
    return "\n".join(
        [
            f"결론: {verdict}",
            f"용의자: {final_report.suspect_id or '없음'}",
            f"근거 증거: {', '.join(final_report.cited_evidence_ids) or '없음'}",
            "불일치:",
            *contradictions,
            "미확인 사항:",
            *unverified,
            "설명:",
            final_report.explanation,
        ]
    )


# 목록 줄 생성
# 문자열 목록을 "- 항목" 줄 목록으로 바꾸고 비어 있으면 "- 없음"을 반환하는 함수
def _bullet_lines(items: list[str]) -> list[str]:
    # 비어 있으면 없음 표시
    if not items:
        return ["- 없음"]
    # 항목마다 한 줄
    return [f"- {item}" for item in items]


# 조사 기록 블록 생성
# 도구 호출 한 번의 순번·도구·인자·사유·결과를 여러 줄 문자열로 만드는 함수
def format_history_entry(entry: HistoryEntry, budget: int) -> str:
    # 인자를 한글 그대로 JSON 문자열로
    args_text = json.dumps(entry["args"], ensure_ascii=False)
    # 결과 문구 선택
    if entry["error"] is not None:
        result = f"오류: {entry['error']}"
    elif entry["evidence_ids"]:
        result = f"증거 {', '.join(entry['evidence_ids'])}"
    elif entry["found"] is None:
        result = "교차 검증 완료"
    else:
        result = "특이사항 없음"
    # 세 줄 블록 조합
    return "\n".join(
        [
            f"[{entry['step']}/{budget}] {entry['tool']} {args_text}",
            f"  사유: {entry['reason']}",
            f"  결과: {result}",
        ]
    )


# 모듈 직접 실행 시 진입점 호출
if __name__ == "__main__":
    sys.exit(main())
