"""수사 실행 함수.

mode="fixed"(고정 계획형)는 비교 실험 전용이며 공개 API로 노출하지 않는다. 서비스에서는 적응형만 쓴다.
"""

from collections.abc import Callable
from typing import Any, Literal, cast

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage

from app.agent.events import EventCallback, EventTranslator
from app.agent.fixed_graph import build_fixed_graph
from app.agent.graph import build_investigation_graph
from app.agent.prompts import SYSTEM_PROMPT, build_case_brief
from app.agent.state import InvestigationState
from app.schemas.case import CaseFile, PublicCase
from app.services.case_repository import CaseRepository

# 실행 방식
InvestigationMode = Literal["adaptive", "fixed"]
# 상태 전달 함수 형식
StateCallback = Callable[[InvestigationState], None]


# 스트리밍 실행 예외
# 그래프 실행 중 예외가 났을 때 마지막 상태와 사용자용 문장을 담아 전달하는 예외 클래스
class InvestigationStreamError(RuntimeError):
    # 예외 생성
    # 마지막으로 받은 상태와 사용자용 문장을 보관하는 함수
    def __init__(self, last_state: InvestigationState, message: str) -> None:
        # 부모 예외에 사용자용 문장 전달
        super().__init__(message)
        # 마지막 상태
        self.last_state = last_state
        # 사용자용 문장
        self.message = message


# 수사 실행
# 사건을 로드해 방식에 맞는 그래프를 끝까지 실행하고 최종 상태를 반환하는 함수
def run_investigation(
    case_id: str,
    llm: BaseChatModel,
    mode: InvestigationMode = "adaptive",
    repository: CaseRepository | None = None,
) -> InvestigationState:
    # 저장소가 없으면 기본 경로 저장소 사용
    repository = repository or CaseRepository()
    # 사건 로드와 공개 정보 변환
    case = repository.load_case(case_id)
    public_case = repository.get_public_case(case_id)

    # 방식별 그래프와 첫 메시지
    if mode == "fixed":
        # 고정 계획형은 planner가 시스템 프롬프트·브리핑을 직접 구성하므로 비워 둠
        graph = build_fixed_graph(llm, case)
        initial_state = build_initial_state(case, mode, [])
    else:
        # 적응형은 시스템 프롬프트 + 사건 브리핑으로 시작
        graph = build_investigation_graph(llm, case)
        initial_state = build_initial_state(
            case, mode, adaptive_initial_messages(public_case)
        )
    # 그래프 실행 후 최종 상태 반환
    result = graph.invoke(
        initial_state, config={"recursion_limit": _recursion_limit(case)}
    )
    return cast(InvestigationState, result)


# 적응형 스트리밍 실행
# 적응형 수사를 같은 초기 상태로 스트리밍 실행하며 이벤트·상태를 콜백으로 넘기고 최종 상태를 반환하는 함수
# 그래프 실행 중 예외가 나면 error 이벤트를 보낸 뒤 InvestigationStreamError를 던진다
def run_investigation_stream(
    case_id: str,
    llm: BaseChatModel,
    on_event: EventCallback,
    repository: CaseRepository | None = None,
    on_state: StateCallback | None = None,
) -> InvestigationState:
    # 저장소가 없으면 기본 경로 저장소 사용
    repository = repository or CaseRepository()
    # 사건 로드와 공개 정보 변환
    case = repository.load_case(case_id)
    public_case = repository.get_public_case(case_id)
    # 적응형 그래프와 초기 상태 (run_investigation과 동일)
    graph = build_investigation_graph(llm, case)
    initial_state = build_initial_state(
        case, "adaptive", adaptive_initial_messages(public_case)
    )
    # 이벤트 변환기와 현재 상태
    translator = EventTranslator(case, on_event)
    current: dict[str, Any] = dict(initial_state)

    # 노드 업데이트와 전체 상태를 함께 받으며 실행
    try:
        for mode, chunk in graph.stream(
            initial_state,
            config={"recursion_limit": _recursion_limit(case)},
            stream_mode=["updates", "values"],
        ):
            if mode == "values":
                # 전체 상태 갱신 후 전달
                current = dict(chunk)
                if on_state is not None:
                    on_state(cast(InvestigationState, current))
            else:
                # 노드 업데이트를 업데이트 직전 상태와 함께 이벤트로 변환
                for node, update in chunk.items():
                    translator.handle_update(node, update, current)
    except Exception as error:
        # 오류 이벤트를 보내고 마지막 상태와 함께 예외 전달
        message = translator.fail(error)
        raise InvestigationStreamError(
            cast(InvestigationState, current), message
        ) from error

    # 종료 이벤트 후 최종 상태 반환
    translator.finish(current)
    return cast(InvestigationState, current)


# 적응형 첫 메시지 생성
# 시스템 프롬프트와 사건 브리핑으로 적응형 수사의 첫 메시지 목록을 만드는 함수
def adaptive_initial_messages(public_case: PublicCase) -> list[AnyMessage]:
    # 시스템 프롬프트 + 브리핑
    return [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=build_case_brief(public_case) + "\n수사를 시작하라."),
    ]


# 초기 상태 생성
# 사건·방식·첫 메시지로 수사 그래프의 초기 상태를 만드는 함수
def build_initial_state(
    case: CaseFile, mode: InvestigationMode, messages: list[AnyMessage]
) -> InvestigationState:
    # 초기 상태 반환
    return {
        "case_id": case.case_id,
        "mode": mode,
        "messages": messages,
        "collected_evidence": {},
        "investigation_history": [],
        "tool_call_count": 0,
        "status": "running",
        "stop_reason": None,
        "plan": None,
        "pending_report": None,
        "final_report": None,
        "report_status": None,
        "validation_rejections": 0,
        "report_errors": [],
        "error": None,
    }


# 반복 한도 계산
# 사건 예산으로 그래프 반복 한도를 계산하는 함수
def _recursion_limit(case: CaseFile) -> int:
    # 예산 × 2(수사관·도구 실행) + 마지막 수사관 1 + 보고서·검증 2회씩 4 + 여유 5
    # (고정 계획형은 계획 1 + 실행 1 + 보고서·검증 4로 이보다 훨씬 적음)
    return case.tool_budget * 2 + 10
