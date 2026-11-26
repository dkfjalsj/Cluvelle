import threading
from datetime import UTC, datetime, timedelta
from typing import Any

from api_helpers import wait_finished

from app.schemas.api import InvestigationEvent
from app.services.investigation_runs import InvestigationRunStore


# 바로 끝나는 실행 함수
# 종료 이벤트 하나를 보내고 완료 상태를 돌려주는 가짜 실행 함수
def quick_runner(case_id: str, llm: Any, on_event: Any, **kwargs: Any) -> Any:
    # 종료 이벤트 전송
    on_event(
        InvestigationEvent(
            id=0,
            event="finished",
            data={
                "status": "completed",
                "stop_reason": "finished",
                "report_status": "accepted",
            },
        )
    )
    # 완료 상태 반환
    return {"case_id": case_id, "status": "completed"}


# 시계 생성
# 바꿀 수 있는 현재 시각 목록과 그 시각을 돌려주는 함수를 만드는 함수
def make_clock() -> tuple[list[datetime], Any]:
    # 시작 시각
    current = [datetime(2026, 11, 26, 12, 0, tzinfo=UTC)]
    return current, lambda: current[0]


# 보관 기간 정리 테스트
# 종료 후 1시간이 지난 실행은 조회 시 삭제되고, 그 전에는 남아 있는지 확인하는 함수
def test_finished_runs_expire_after_one_hour() -> None:
    current, now = make_clock()
    store = InvestigationRunStore(now=now, runner=quick_runner)
    run = store.start("CASE-001", None)  # type: ignore[arg-type]
    wait_finished(run)
    # 59분 뒤에는 남아 있음
    current[0] += timedelta(minutes=59)
    assert store.get(run.investigation_id) is not None
    # 1시간 뒤에는 삭제
    current[0] += timedelta(minutes=1)
    assert store.get(run.investigation_id) is None


# 최대 건수 정리 테스트
# 50건을 넘으면 가장 오래된 종료 실행부터 지우고 진행 중인 실행은 유지하는지 확인하는 함수
def test_max_runs_removes_oldest_finished_keeps_running() -> None:
    current, now = make_clock()
    release = threading.Event()

    # 첫 실행만 멈추는 실행 함수
    # 첫 호출은 해제 신호까지 기다리고 나머지는 바로 끝내는 함수
    def runner(case_id: str, llm: Any, on_event: Any, **kwargs: Any) -> Any:
        # 진행 중으로 남길 실행
        if case_id == "CASE-002":
            release.wait(10)
        return quick_runner(case_id, llm, on_event, **kwargs)

    store = InvestigationRunStore(now=now, runner=runner)
    # 가장 오래된 진행 중 실행
    running = store.start("CASE-002", None)  # type: ignore[arg-type]
    # 종료 실행 50건 (생성 시각을 1초씩 늘림)
    finished_runs = []
    for _ in range(50):
        current[0] += timedelta(seconds=1)
        run = store.start("CASE-001", None)  # type: ignore[arg-type]
        wait_finished(run)
        finished_runs.append(run)
    # 51건 → 정리 시 가장 오래된 종료 실행 1건 삭제, 진행 중은 유지
    assert store.get(running.investigation_id) is not None
    assert store.get(finished_runs[0].investigation_id) is None
    assert store.get(finished_runs[1].investigation_id) is not None
    # 정리
    release.set()
    wait_finished(running)
