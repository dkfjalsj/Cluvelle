import json
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from agent_fakes import (
    ScriptedChatModel,
    accuse_report,
    finish_message,
    tool_call_message,
)
from fastapi.testclient import TestClient
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage

from app.agent.runner import run_investigation_stream
from app.api.investigations import get_model_factory, get_rate_limiter, get_run_store
from app.main import app
from app.services.investigation_runs import InvestigationRun, InvestigationRunStore
from app.services.rate_limit import RateLimiter


# 짧은 각본
# 현장 조사 2회와 교차 검증 없이 수사를 마치는 짧은 CASE-001 각본을 만드는 함수
def short_script() -> list[AIMessage]:
    # 현장 조사 2회 + 수사 종료
    return [
        tool_call_message(
            "inspect_scene",
            {
                "location_id": "L1",
                "reason": "보관함 상태 확인",
                "hypothesis": "아직 가설 없음",
            },
            "c1",
        ),
        tool_call_message(
            "check_cctv",
            {
                "camera_id": "C3",
                "time_window": "22:00-23:00",
                "reason": "주차장 출입구 확인",
                "hypothesis": "외부 경로로 반출되었다",
            },
            "c2",
        ),
        finish_message(),
    ]


# 짧은 각본 모델 생성 함수
# 호출할 때마다 새 각본 모델(짧은 각본 + S3 지목 보고서)을 만드는 함수
def short_model_factory() -> BaseChatModel:
    # 새 각본 모델 반환
    return ScriptedChatModel(
        responses=short_script(), reports=[accuse_report("S3", ["E1", "E19"])]
    )


# 넉넉한 제한기 생성
# 테스트가 제한에 걸리지 않도록 상한을 크게 잡은 제한기를 만드는 함수
def generous_limiter() -> RateLimiter:
    # 큰 상한의 제한기 반환
    return RateLimiter(
        max_concurrent_runs=100, daily_runs_total=1000, daily_runs_per_ip=1000
    )


# 테스트 클라이언트
# 저장소·제한기·모델 생성 함수를 교체한 테스트 클라이언트를 만들고 끝나면 교체를 되돌리는 함수
@contextmanager
def api_client(
    store: InvestigationRunStore | None = None,
    limiter: RateLimiter | None = None,
    model_factory: Callable[[], BaseChatModel] = short_model_factory,
) -> Iterator[TestClient]:
    # 의존성 교체
    store = store or InvestigationRunStore()
    limiter = limiter or generous_limiter()
    app.dependency_overrides[get_run_store] = lambda: store
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    app.dependency_overrides[get_model_factory] = lambda: model_factory
    try:
        yield TestClient(app)
    finally:
        # 교체 되돌리기
        app.dependency_overrides.clear()


# SSE 읽기
# SSE 응답을 끝까지 읽어 (원문, 이벤트 목록)을 반환하는 함수
def read_sse(
    client: TestClient, url: str, **kwargs: Any
) -> tuple[str, list[dict[str, Any]]]:
    # 스트림 전체 원문 읽기
    with client.stream("GET", url, **kwargs) as response:
        assert response.status_code == 200
        raw = "".join(response.iter_text())
    # 빈 줄로 나눈 블록을 이벤트로 해석 (주석 줄 제외)
    events: list[dict[str, Any]] = []
    for block in raw.split("\n\n"):
        lines = [
            line for line in block.splitlines() if line and not line.startswith(":")
        ]
        if not lines:
            continue
        fields = dict(line.split(": ", 1) for line in lines)
        events.append(
            {
                "id": int(fields["id"]),
                "event": fields["event"],
                "data": json.loads(fields["data"]),
            }
        )
    return raw, events


# 실행 종료 기다리기
# 실행이 종료 상태가 될 때까지 최대 timeout초 기다리는 함수
def wait_finished(run: InvestigationRun, timeout: float = 10.0) -> None:
    # 마감 시각
    deadline = time.monotonic() + timeout
    with run.condition:
        while not run.finished:
            remaining = deadline - time.monotonic()
            assert remaining > 0, "실행이 제한 시간 안에 끝나지 않았습니다."
            run.condition.wait(remaining)


# 멈춤 실행 함수 생성
# 해제 신호를 받을 때까지 기다렸다가 실제 스트리밍 실행을 하는 실행 함수와 신호를 만드는 함수
def blocking_runner() -> tuple[Callable[..., Any], threading.Event]:
    # 해제 신호
    release = threading.Event()

    # 멈춤 실행
    # 해제 신호를 기다린 뒤 실제 스트리밍 실행을 하는 함수
    def runner(*args: Any, **kwargs: Any) -> Any:
        # 해제될 때까지 대기 (최대 10초)
        release.wait(10)
        return run_investigation_stream(*args, **kwargs)

    # 실행 함수와 신호 반환
    return runner, release
