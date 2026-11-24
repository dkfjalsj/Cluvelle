from collections.abc import Sequence
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field


# 각본 채팅 모델
# 미리 준 AIMessage를 호출 순서대로 돌려주는 네트워크 없는 가짜 LLM 클래스
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
