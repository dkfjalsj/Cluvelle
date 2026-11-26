from collections.abc import Callable
from typing import Any

from langchain_core.messages import AIMessage
from pydantic import BaseModel

from app.agent.graph import INVESTIGATOR_NODE, TOOL_EXECUTOR_NODE
from app.agent.tool_specs import NON_TOOL_ARG_FIELDS, valid_hypothesis
from app.schemas.api import (
    ErrorData,
    EventType,
    EvidenceFoundData,
    FinishedData,
    HypothesisUpdatedData,
    InvestigationEvent,
    ToolSelectedData,
)
from app.schemas.case import CaseFile
from app.schemas.tool import EvidenceView

# 이벤트 전달 함수 형식
EventCallback = Callable[[InvestigationEvent], None]
# 그래프 예외 시 사용자용 문장 형식
STREAM_ERROR_MESSAGE = "수사 실행 중 오류가 발생했습니다. ({error_type})"


# 이벤트 변환기
# 그래프 노드 업데이트를 번호가 붙은 수사 이벤트로 바꿔 전달하는 클래스
class EventTranslator:
    # 변환기 생성
    # 사건과 이벤트 전달 함수를 받아 변환기를 초기화하는 함수
    def __init__(self, case: CaseFile, on_event: EventCallback) -> None:
        # 사건 (예산·순번 계산용)
        self.case = case
        # 이벤트 전달 함수
        self.on_event = on_event
        # 다음 이벤트 번호
        self.next_id = 0
        # 직전에 보낸 가설
        self.last_hypothesis: str | None = None

    # 노드 업데이트 처리
    # 노드 이름과 업데이트, 업데이트 직전 상태를 받아 해당 이벤트를 보내는 함수
    def handle_update(
        self, node: str, update: dict[str, Any] | None, before: dict[str, Any]
    ) -> None:
        # 업데이트가 없으면 무시
        if not update:
            return
        # 수사관 노드면 도구 선택·가설 이벤트
        if node == INVESTIGATOR_NODE:
            self._handle_investigator(update, before)
        # 도구 실행 노드면 증거 이벤트
        elif node == TOOL_EXECUTOR_NODE:
            self._handle_tool_executor(update, before)

    # 종료 이벤트 보내기
    # 최종 상태의 진행 상태·종료 사유·보고서 처리 결과로 finished 이벤트를 보내는 함수
    def finish(self, state: dict[str, Any]) -> None:
        # 종료 데이터 생성 후 전송
        data = FinishedData(
            status=state["status"],
            stop_reason=state.get("stop_reason"),
            report_status=state.get("report_status"),
        )
        self._emit("finished", data)

    # 오류 이벤트 보내기
    # 예외 종류만 담은 사용자용 문장으로 error 이벤트를 보내고 그 문장을 반환하는 함수
    def fail(self, error: Exception) -> str:
        # 예외 메시지 본문은 내보내지 않고 종류만 표시
        message = STREAM_ERROR_MESSAGE.format(error_type=type(error).__name__)
        self._emit("error", ErrorData(message=message))
        # 사용자용 문장 반환
        return message

    # 수사관 업데이트 처리
    # 수사관이 낸 도구 호출마다 tool_selected와 (가설이 바뀌면) hypothesis_updated를 보내는 함수
    def _handle_investigator(
        self, update: dict[str, Any], before: dict[str, Any]
    ) -> None:
        # 마지막 AIMessage의 도구 호출 목록
        messages = update.get("messages") or []
        last = messages[-1] if messages else None
        if not isinstance(last, AIMessage) or not last.tool_calls:
            return
        # 업데이트 직전 호출 횟수
        count = before["tool_call_count"]
        # 호출마다 예정 순번 계산 (예산을 넘는 호출은 실행되지 않으므로 이벤트 없음)
        for index, tool_call in enumerate(last.tool_calls):
            step = count + index + 1
            if step > self.case.tool_budget:
                break
            # 도구 선택 이벤트 (reason·hypothesis 제외 인자)
            raw_args = dict(tool_call.get("args") or {})
            raw_reason = raw_args.get("reason")
            self._emit(
                "tool_selected",
                ToolSelectedData(
                    step=step,
                    tool=tool_call["name"],
                    args={
                        key: value
                        for key, value in raw_args.items()
                        if key not in NON_TOOL_ARG_FIELDS
                    },
                    reason=raw_reason if isinstance(raw_reason, str) else None,
                ),
            )
            # 유효한 가설이 직전과 다를 때만 가설 이벤트
            hypothesis = valid_hypothesis(raw_args.get("hypothesis"))
            if hypothesis is not None and hypothesis != self.last_hypothesis:
                self._emit(
                    "hypothesis_updated",
                    HypothesisUpdatedData(step=step, hypothesis=hypothesis),
                )
                self.last_hypothesis = hypothesis

    # 도구 실행 업데이트 처리
    # 이번에 새로 생긴 조사 기록마다 evidence_found 이벤트를 보내는 함수
    def _handle_tool_executor(
        self, update: dict[str, Any], before: dict[str, Any]
    ) -> None:
        # 새로 추가된 조사 기록
        history = update.get("investigation_history") or []
        new_entries = history[len(before["investigation_history"]) :]
        # 확보 증거 조회 표 (갱신된 값)
        collected = update.get("collected_evidence") or {}
        # 기록마다 증거 이벤트
        for entry in new_entries:
            evidence = [
                EvidenceView(
                    id=collected[evidence_id]["id"],
                    source_tool=collected[evidence_id]["source_tool"],
                    summary=collected[evidence_id]["summary"],
                )
                for evidence_id in entry["evidence_ids"]
                if evidence_id in collected
            ]
            self._emit(
                "evidence_found",
                EvidenceFoundData(
                    step=entry["step"],
                    tool=entry["tool"],
                    found=entry["found"],
                    evidence=evidence,
                    error=entry["error"],
                    remaining_budget=max(self.case.tool_budget - entry["step"], 0),
                ),
            )

    # 이벤트 전송
    # 번호를 붙인 이벤트를 만들어 전달하고 번호를 1 늘리는 함수
    def _emit(self, event: EventType, data: BaseModel) -> None:
        # 이벤트 생성 후 전달
        self.on_event(
            InvestigationEvent(
                id=self.next_id, event=event, data=data.model_dump(mode="json")
            )
        )
        # 다음 번호
        self.next_id += 1
