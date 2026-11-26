import json
from collections.abc import Callable, Iterator
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse
from langchain_core.language_models import BaseChatModel

from app.agent.llm import MissingApiKeyError, create_chat_model
from app.api.cases import RepositoryDep, http_error, load_case_or_raise
from app.config import get_settings
from app.schemas.api import (
    CollectedEvidenceItem,
    HistoryItem,
    InvestigationEvent,
    InvestigationResultResponse,
    StartInvestigationRequest,
    StartInvestigationResponse,
)
from app.services.grading import grade_final_state
from app.services.investigation_runs import InvestigationRun, InvestigationRunStore
from app.services.rate_limit import RateLimiter, RateLimitExceeded, get_client_ip

# 수사 라우터
router = APIRouter()

# 새 이벤트가 없을 때 연결 유지 주석을 보내는 간격(초)
PING_INTERVAL_SECONDS = 15.0
# 스트림을 닫는 마지막 이벤트 종류
TERMINAL_EVENTS = {"finished", "error"}
# SSE 응답 헤더
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}

# 모델 생성 함수 형식
ModelFactory = Callable[[], BaseChatModel]


# 모델 생성 함수 의존성
# 설정으로 Gemini 채팅 모델을 만드는 함수를 반환하는 함수 (테스트에서 가짜 LLM으로 교체)
def get_model_factory() -> ModelFactory:
    # 호출할 때 설정을 읽어 모델 생성
    return lambda: create_chat_model(get_settings())


# 수사 실행 저장소 의존성
# 프로세스 하나에서 공유하는 수사 실행 저장소를 반환하는 함수
@lru_cache
def get_run_store() -> InvestigationRunStore:
    # 웹 수사는 예산을 모두 쓰도록 재촉하는 저장소 생성
    return InvestigationRunStore(use_full_budget=True)


# 실행 제한기 의존성
# 설정의 상한 값으로 만든 프로세스 공유 실행 제한기를 반환하는 함수
@lru_cache
def get_rate_limiter() -> RateLimiter:
    # 설정 값으로 제한기 생성
    settings = get_settings()
    return RateLimiter(
        max_concurrent_runs=settings.max_concurrent_runs,
        daily_runs_total=settings.daily_runs_total,
        daily_runs_per_ip=settings.daily_runs_per_ip,
    )


# 수사 실행 저장소 의존성 주입 형식
StoreDep = Annotated[InvestigationRunStore, Depends(get_run_store)]


# 수사 시작
# 사건 확인 → 모델 생성 → 실행 제한 확인 순서로 검사한 뒤 적응형 수사를 백그라운드에서 시작하는 함수
@router.post("/api/investigations", status_code=201)
def start_investigation(
    body: StartInvestigationRequest,
    request: Request,
    repository: RepositoryDep,
    model_factory: Annotated[ModelFactory, Depends(get_model_factory)],
    store: StoreDep,
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> StartInvestigationResponse:
    # 사건 존재·형식 확인 (400/404)
    load_case_or_raise(repository, body.case_id)
    # 모델 생성 (키가 없으면 503, 횟수에 세지 않음)
    try:
        llm = model_factory()
    except MissingApiKeyError as error:
        raise http_error(
            503, "llm_unavailable", "AI 모델 설정이 없어 수사를 시작할 수 없습니다."
        ) from error
    # 접속 IP
    client_ip = get_client_ip(request)
    # 제한 확인 → 시작 → 횟수 기록을 한 번에 처리
    with limiter.lock:
        try:
            limiter.check(client_ip, store.active_count())
        except RateLimitExceeded as error:
            raise http_error(429, error.code, error.message) from error
        run = store.start(body.case_id, llm)
        limiter.record(client_ip)
    # 시작 응답
    return StartInvestigationResponse(
        investigation_id=run.investigation_id,
        case_id=run.case_id,
        status=run.status,
    )


# 수사 이벤트 스트림
# 지정한 번호 다음부터 수사 이벤트를 SSE로 보내고 마지막 이벤트 뒤에 닫는 함수
@router.get("/api/investigations/{investigation_id}/events")
def stream_events(
    investigation_id: str,
    store: StoreDep,
    last_event_id_header: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    last_event_id: Annotated[int | None, Query()] = None,
) -> StreamingResponse:
    # 실행 조회 (없으면 404)
    run = _get_run_or_raise(store, investigation_id)
    # 이어 받을 시작 번호
    start = _resume_index(last_event_id_header, last_event_id)
    # SSE 스트림 응답
    return StreamingResponse(
        _event_stream(store, run, start),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


# 수사 결과 조회
# 진행 상태·조사 기록·확보 증거와, 종료 후에만 보고서·채점 결과를 반환하는 함수
@router.get("/api/investigations/{investigation_id}/result")
def get_result(
    investigation_id: str,
    repository: RepositoryDep,
    store: StoreDep,
) -> InvestigationResultResponse:
    # 실행 조회 (없으면 404)
    run = _get_run_or_raise(store, investigation_id)
    # 사건 예산
    case = repository.load_case(run.case_id)
    # 최근 상태 (아직 없으면 빈 값)
    state = dict(run.state or {})
    finished = run.finished
    # 조사 기록·확보 증거
    history = [HistoryItem(**entry) for entry in state.get("investigation_history", [])]
    collected = [
        CollectedEvidenceItem(**item)
        for item in state.get("collected_evidence", {}).values()
    ]
    # 결과 응답 (보고서·채점은 종료 후에만)
    return InvestigationResultResponse(
        investigation_id=run.investigation_id,
        case_id=run.case_id,
        status=run.status,
        tool_budget=case.tool_budget,
        tool_call_count=int(state.get("tool_call_count") or 0),
        history=history,
        collected_evidence=collected,
        final_report=state.get("final_report") if finished else None,
        report_status=state.get("report_status") if finished else None,
        validation_rejections=(
            int(state.get("validation_rejections") or 0) if finished else None
        ),
        error=run.error,
        grading=(
            grade_final_state({**state, "case_id": run.case_id, "status": run.status})
            if finished
            else None
        ),
    )


# 실행 조회 (오류 응답 변환)
# 수사 ID로 실행을 찾고 없으면 404 응답 예외를 내는 함수
def _get_run_or_raise(
    store: InvestigationRunStore, investigation_id: str
) -> InvestigationRun:
    # 실행 조회
    run = store.get(investigation_id)
    if run is None:
        raise http_error(404, "investigation_not_found", "수사를 찾을 수 없습니다.")
    # 실행 반환
    return run


# 이어 받기 시작 번호
# Last-Event-ID 헤더(우선) 또는 last_event_id 쿼리로 다음에 보낼 이벤트 번호를 계산하는 함수
def _resume_index(header_value: str | None, query_value: int | None) -> int:
    # 헤더가 정수면 그 다음 번호
    if header_value is not None and header_value.strip().lstrip("-").isdigit():
        return max(int(header_value.strip()) + 1, 0)
    # 쿼리가 있으면 그 다음 번호
    if query_value is not None:
        return max(query_value + 1, 0)
    # 없으면 처음부터
    return 0


# SSE 스트림 생성
# 새 이벤트를 SSE 형식으로 보내고, 없으면 주기적으로 ping 주석을 보내며, 마지막 이벤트 뒤에 끝나는 함수
def _event_stream(
    store: InvestigationRunStore, run: InvestigationRun, start: int
) -> Iterator[str]:
    # 다음에 보낼 번호
    next_index = start
    while True:
        # 새 이벤트 기다리기
        events = store.wait_for_events(run, next_index, PING_INTERVAL_SECONDS)
        if not events:
            # 이미 끝났고 보낼 이벤트가 없으면 종료
            if run.finished:
                return
            # 진행 중이면 연결 유지 주석
            yield ": ping\n\n"
            continue
        # 이벤트를 순서대로 보내고 마지막 이벤트면 종료
        for event in events:
            yield _format_event(event)
            next_index = event.id + 1
            if event.event in TERMINAL_EVENTS:
                return


# SSE 이벤트 문자열
# 이벤트 하나를 id·event·data 줄과 빈 줄로 이루어진 SSE 문자열로 만드는 함수
def _format_event(event: InvestigationEvent) -> str:
    # 데이터는 한 줄 JSON (한글 그대로)
    data_line = json.dumps(event.data, ensure_ascii=False, separators=(",", ":"))
    # SSE 형식 문자열 반환
    return f"id: {event.id}\nevent: {event.event}\ndata: {data_line}\n\n"
