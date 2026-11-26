from collections.abc import Sequence
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel, Field, ValidationError

from app.schemas.plan import InvestigationPlan
from app.schemas.report import FinalReport

# 수사 종료 응답 문구
FINISH_TEXT = "수사를 마칩니다."
# 테스트용 기본 가설
DEFAULT_HYPOTHESIS = "테스트 가설"


# 도구 호출 메시지 생성
# 도구 호출 하나를 담은 AIMessage를 만드는 함수 (reason이 있고 hypothesis가 없으면 기본 가설 추가)
def tool_call_message(name: str, args: dict[str, Any], call_id: str) -> AIMessage:
    # 이유가 있는 호출에는 기본 가설을 채움 (가설 누락을 시험할 때는 reason도 빼거나 직접 구성)
    call_args = dict(args)
    if "reason" in call_args and "hypothesis" not in call_args:
        call_args["hypothesis"] = DEFAULT_HYPOTHESIS
    # 도구 호출 하나짜리 AIMessage 반환
    return AIMessage(
        content="", tool_calls=[{"name": name, "args": call_args, "id": call_id}]
    )


# 수사 종료 메시지 생성
# 도구 호출 없이 수사 종료 문구만 담은 AIMessage를 만드는 함수
def finish_message() -> AIMessage:
    # 수사 종료 AIMessage 반환
    return AIMessage(content=FINISH_TEXT)


# 지목 보고서 생성
# 용의자와 근거 증거를 받아 지목 보고서를 만드는 함수
def accuse_report(suspect_id: str, evidence_ids: list[str]) -> FinalReport:
    # 지목 보고서 반환
    return FinalReport(
        verdict="accuse",
        suspect_id=suspect_id,
        cited_evidence_ids=evidence_ids,
        contradictions=["테스트 불일치"],
        unverified=[],
        explanation="테스트 설명",
    )


# 판단 보류 보고서 생성
# 근거 증거를 받아 판단 보류 보고서를 만드는 함수
def withhold_report(evidence_ids: list[str] | None = None) -> FinalReport:
    # 판단 보류 보고서 반환
    return FinalReport(
        verdict="withhold",
        suspect_id=None,
        cited_evidence_ids=evidence_ids or [],
        contradictions=[],
        unverified=["테스트 미확인 사항"],
        explanation="테스트 보류 설명",
    )


# 각본 채팅 모델
# 미리 준 AIMessage와 보고서를 호출 순서대로 돌려주는 네트워크 없는 가짜 LLM 클래스
class ScriptedChatModel(BaseChatModel):
    # 호출 순서대로 돌려줄 응답 목록
    responses: list[AIMessage] = Field(default_factory=list)
    # 목록이 끝나면 마지막 응답을 계속 돌려줄지 여부
    repeat_last: bool = False
    # 호출 시 던질 예외 (있으면 응답 대신 예외 발생)
    error: Exception | None = None
    # 호출마다 받은 메시지 기록
    received: list[list[BaseMessage]] = Field(default_factory=list)
    # 지금까지 호출된 횟수
    call_count: int = 0
    # 보고서 각본 (보고서 객체, 형식 오류를 일으킬 dict, 또는 예외)
    reports: list[Any] = Field(default_factory=list)
    # 보고서 요청마다 받은 메시지 기록
    report_received: list[list[BaseMessage]] = Field(default_factory=list)
    # 지금까지 보고서 요청된 횟수
    report_call_count: int = 0
    # 계획 각본 (계획 객체, 형식 오류를 일으킬 dict, 또는 예외)
    plans: list[Any] = Field(default_factory=list)
    # 계획 요청마다 받은 메시지 기록
    plan_received: list[list[BaseMessage]] = Field(default_factory=list)
    # 지금까지 계획 요청된 횟수
    plan_call_count: int = 0

    # 모델 종류 이름
    # LangChain이 요구하는 모델 식별 문자열을 반환하는 함수
    @property
    def _llm_type(self) -> str:
        # 고정 식별 문자열 반환
        return "scripted-chat-model"

    # 도구 묶기
    # 도구 명세를 무시하고 자기 자신을 반환하는 함수
    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "ScriptedChatModel":
        # 각본대로만 응답하므로 자신 반환
        return self

    # 구조화 출력 실행 객체 생성
    # 보고서 각본을 호출 순서대로 돌려주는 실행 객체를 반환하는 함수
    def with_structured_output(
        self,
        schema: Any,
        *,
        include_raw: bool = False,
        **kwargs: Any,
    ) -> Runnable[Any, Any]:
        # 계획 스키마인지 여부 (계획과 보고서는 각본 목록을 따로 씀)
        is_plan = schema is InvestigationPlan

        # 구조화 출력 요청 처리
        # 받은 메시지를 기록하고 스키마에 맞는 각본의 다음 항목을 구조화 출력 형식으로 돌려주는 함수
        def respond(messages: Any) -> Any:
            # 스키마별 기록·각본·횟수 선택 후 다음 항목 꺼내기
            if is_plan:
                self.plan_received.append(list(messages))
                if self.plan_call_count >= len(self.plans):
                    raise RuntimeError("계획 각본을 모두 사용했습니다.")
                item = self.plans[self.plan_call_count]
                self.plan_call_count += 1
            else:
                self.report_received.append(list(messages))
                if self.report_call_count >= len(self.reports):
                    raise RuntimeError("보고서 각본을 모두 사용했습니다.")
                item = self.reports[self.report_call_count]
                self.report_call_count += 1
            # 예외 항목이면 그대로 던짐
            if isinstance(item, Exception):
                raise item
            # 보고서 객체면 정상 결과
            if isinstance(item, BaseModel):
                raw = AIMessage(content=item.model_dump_json())
                parsed: Any = item
                parsing_error: Exception | None = None
            else:
                # 그 외 값은 스키마로 검증해 형식 오류 재현
                raw = AIMessage(content=str(item))
                try:
                    parsed = schema.model_validate(item)
                    parsing_error = None
                except ValidationError as error:
                    parsed = None
                    parsing_error = error
            # include_raw면 원문·파싱 결과·오류를 함께 반환
            if include_raw:
                return {"raw": raw, "parsed": parsed, "parsing_error": parsing_error}
            # 아니면 파싱 결과만 반환 (오류면 예외)
            if parsing_error is not None:
                raise parsing_error
            return parsed

        # 실행 객체로 감싸 반환
        return RunnableLambda(respond)

    # 응답 생성
    # 받은 메시지를 기록하고 각본의 다음 응답(또는 예외)을 돌려주는 함수
    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        # 받은 메시지 기록
        self.received.append(list(messages))
        # 예외 옵션이면 예외 발생
        if self.error is not None:
            raise self.error
        # 다음 응답 선택 (끝나면 마지막 응답 반복 또는 오류)
        if self.call_count < len(self.responses):
            message = self.responses[self.call_count]
        elif self.repeat_last and self.responses:
            message = self.responses[-1]
        else:
            raise RuntimeError("각본의 응답을 모두 사용했습니다.")
        # 호출 횟수 증가
        self.call_count += 1
        # 메시지 ID가 겹치지 않도록 ID 없는 복사본 반환
        reply = message.model_copy(update={"id": None})
        return ChatResult(generations=[ChatGeneration(message=reply)])
