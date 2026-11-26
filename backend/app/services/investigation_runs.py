"""수사 실행 관리.

서버 프로세스 하나(worker 1개)의 메모리에 실행을 보관한다. 서버가 재시작되면 실행 정보는 사라진다.
"""

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from langchain_core.language_models import BaseChatModel

from app.agent.runner import InvestigationStreamError, run_investigation_stream
from app.agent.state import InvestigationState
from app.schemas.api import ErrorData, InvestigationEvent, RunStatus
from app.services.rate_limit import now_kst

# 종료 후 보관 기간
DEFAULT_RETENTION = timedelta(hours=1)
# 최대 보관 건수
DEFAULT_MAX_RUNS = 50
# 종료 상태
FINISHED_STATUSES = {"completed", "inconclusive", "failed"}
# 그래프 안에서 처리된 실패의 사용자용 문장 형식
LLM_FAILURE_MESSAGE = "AI 모델 호출에 실패했습니다. ({error_type})"
# 원인을 알 수 없는 실패 문장
UNKNOWN_FAILURE_MESSAGE = "수사를 완료하지 못했습니다."

# 스트리밍 실행 함수 형식
StreamRunner = Callable[..., InvestigationState]


# 수사 실행
# 실행 하나의 사건·시각·상태·이벤트·최종 상태·오류 문장을 담는 클래스
@dataclass
class InvestigationRun:
    # 수사 ID
    investigation_id: str
    # 사건 ID
    case_id: str
    # 생성 시각
    created_at: datetime
    # 진행 상태
    status: RunStatus = "pending"
    # 지금까지의 이벤트
    events: list[InvestigationEvent] = field(default_factory=list)
    # 최근(또는 최종) 상태
    state: InvestigationState | None = None
    # 사용자용 오류 문장
    error: str | None = None
    # 종료 시각
    finished_at: datetime | None = None
    # 새 이벤트·종료 알림용 조건 변수
    condition: threading.Condition = field(default_factory=threading.Condition)

    # 종료 여부
    # 실행이 종료 상태인지 반환하는 함수
    @property
    def finished(self) -> bool:
        # 종료 상태 집합에 있는지 반환
        return self.status in FINISHED_STATUSES


# 수사 실행 저장소
# 수사를 백그라운드 스레드로 실행하고 실행 정보를 메모리에 보관·정리하는 클래스
class InvestigationRunStore:
    # 저장소 생성
    # 현재 시각 함수·보관 기간·최대 건수·스트리밍 실행 함수를 받아 초기화하는 함수
    def __init__(
        self,
        now: Callable[[], datetime] = now_kst,
        retention: timedelta = DEFAULT_RETENTION,
        max_runs: int = DEFAULT_MAX_RUNS,
        runner: StreamRunner = run_investigation_stream,
    ) -> None:
        # 현재 시각 함수 (테스트에서 주입)
        self.now = now
        # 보관 기간과 최대 건수
        self.retention = retention
        self.max_runs = max_runs
        # 스트리밍 실행 함수
        self.runner = runner
        # 수사 ID → 실행
        self._runs: dict[str, InvestigationRun] = {}
        # 저장소 잠금
        self._lock = threading.Lock()

    # 수사 시작
    # 실행을 만들어 등록하고 백그라운드 스레드에서 스트리밍 실행을 시작하는 함수
    def start(self, case_id: str, llm: BaseChatModel) -> InvestigationRun:
        # 시작 전에 오래된 실행 정리
        self.cleanup()
        # 실행 생성·등록
        run = InvestigationRun(
            investigation_id=str(uuid.uuid4()),
            case_id=case_id,
            created_at=self.now(),
        )
        with self._lock:
            self._runs[run.investigation_id] = run
        # 백그라운드 스레드 시작
        thread = threading.Thread(target=self._execute, args=(run, llm), daemon=True)
        thread.start()
        # 실행 반환
        return run

    # 실행 조회
    # 오래된 실행을 정리한 뒤 수사 ID로 실행을 반환하는 함수 (없으면 None)
    def get(self, investigation_id: str) -> InvestigationRun | None:
        # 조회 전에 정리
        self.cleanup()
        # 실행 반환
        with self._lock:
            return self._runs.get(investigation_id)

    # 진행 중 실행 수
    # 아직 종료되지 않은 실행 수를 반환하는 함수
    def active_count(self) -> int:
        # 종료되지 않은 실행 수 반환
        with self._lock:
            return sum(not run.finished for run in self._runs.values())

    # 오래된 실행 정리
    # 종료 후 보관 기간이 지난 실행을 지우고, 최대 건수를 넘으면 오래된 종료 실행부터 지우는 함수
    def cleanup(self) -> None:
        # 현재 시각
        now = self.now()
        with self._lock:
            # 보관 기간이 지난 종료 실행 삭제
            expired = [
                run_id
                for run_id, run in self._runs.items()
                if run.finished
                and run.finished_at is not None
                and now - run.finished_at >= self.retention
            ]
            for run_id in expired:
                del self._runs[run_id]
            # 최대 건수를 넘으면 생성 순서가 오래된 종료 실행부터 삭제 (진행 중은 유지)
            finished = sorted(
                (run for run in self._runs.values() if run.finished),
                key=lambda run: run.created_at,
            )
            while len(self._runs) > self.max_runs and finished:
                del self._runs[finished.pop(0).investigation_id]

    # 이벤트 기다리기
    # 지정한 번호 이후의 이벤트를 꺼내고, 없으면 제한 시간까지 기다렸다가 꺼내는 함수
    def wait_for_events(
        self, run: InvestigationRun, start: int, timeout: float
    ) -> list[InvestigationEvent]:
        # 조건 변수 아래에서 확인·대기
        with run.condition:
            # 새 이벤트가 없고 아직 진행 중이면 대기
            if len(run.events) <= start and not run.finished:
                run.condition.wait(timeout)
            # 시작 번호 이후 이벤트 반환
            return list(run.events[start:])

    # 백그라운드 실행
    # 스트리밍 실행으로 이벤트·상태를 모으고 종료 상태와 오류 문장을 기록하는 함수
    def _execute(self, run: InvestigationRun, llm: BaseChatModel) -> None:
        # 진행 중으로 변경
        run.status = "running"
        try:
            # 스트리밍 실행 (이벤트·상태를 실행에 반영)
            final = self.runner(
                run.case_id,
                llm,
                on_event=lambda event: self._append_event(run, event),
                on_state=lambda state: setattr(run, "state", state),
            )
        except InvestigationStreamError as error:
            # 그래프 예외: 마지막 상태와 사용자용 문장 보관
            run.state = error.last_state
            self._finish(run, "failed", error.message)
        except Exception as error:  # noqa: BLE001
            # 그래프 밖 예외: 오류 이벤트를 직접 추가해 스트림을 닫게 함
            message = f"수사 실행 중 오류가 발생했습니다. ({type(error).__name__})"
            self._append_event(
                run,
                InvestigationEvent(
                    id=len(run.events),
                    event="error",
                    data=ErrorData(message=message).model_dump(),
                ),
            )
            self._finish(run, "failed", message)
        else:
            # 정상 종료: 최종 상태로 종료 상태·오류 문장 결정
            run.state = final
            status = final["status"]
            if status not in FINISHED_STATUSES:
                status = "failed"
            self._finish(
                run, status, _user_error(final) if status == "failed" else None
            )

    # 이벤트 추가
    # 실행에 이벤트를 추가하고 기다리는 스트림에 알리는 함수
    def _append_event(self, run: InvestigationRun, event: InvestigationEvent) -> None:
        # 조건 변수 아래에서 추가·알림
        with run.condition:
            run.events.append(event)
            run.condition.notify_all()

    # 종료 기록
    # 실행의 종료 상태·오류 문장·종료 시각을 기록하고 기다리는 스트림에 알리는 함수
    def _finish(
        self, run: InvestigationRun, status: RunStatus, error: str | None
    ) -> None:
        # 조건 변수 아래에서 기록·알림
        with run.condition:
            run.status = status
            run.error = error
            run.finished_at = self.now()
            run.condition.notify_all()


# 사용자용 오류 문장
# 그래프 안에서 처리된 실패 상태의 오류를 예외 종류만 담은 고정 문장으로 바꾸는 함수
def _user_error(state: InvestigationState) -> str:
    # 상태의 오류 ("예외 종류: 내용" 형식)
    raw = state.get("error")
    if not raw:
        return UNKNOWN_FAILURE_MESSAGE
    # 예외 종류만 꺼내 고정 문장에 넣음
    error_type = raw.split(":", 1)[0].strip() or "Error"
    return LLM_FAILURE_MESSAGE.format(error_type=error_type)
