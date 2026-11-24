import pytest
from langchain_google_genai import ChatGoogleGenerativeAI

from app.agent.llm import MissingApiKeyError, create_chat_model
from app.config import Settings


# 테스트용 설정 생성
# .env 파일을 읽지 않고 주어진 API 키로 설정 객체를 만드는 함수
def make_settings(api_key: str | None) -> Settings:
    # .env를 무시하고 명시한 값만 사용
    return Settings(_env_file=None, gemini_api_key=api_key)


# 키 누락 테스트
# API 키가 없거나 공백이면 MissingApiKeyError가 나는지 확인하는 함수
@pytest.mark.parametrize("api_key", [None, "", "   "])
def test_missing_api_key(api_key: str | None) -> None:
    # 키 누락 예외 발생 확인
    with pytest.raises(MissingApiKeyError):
        create_chat_model(make_settings(api_key))


# 더미 키 생성 테스트
# 더미 키로 네트워크 호출 없이 모델 객체가 만들어지고 모델명이 설정값과 같은지 확인하는 함수
def test_create_with_dummy_key() -> None:
    # 더미 키 설정
    settings = make_settings("dummy-test-key")
    # 모델 생성 (호출하지 않으므로 네트워크 사용 없음)
    model = create_chat_model(settings)
    # Gemini 모델 객체이고 모델명이 설정값과 같은지 확인
    assert isinstance(model, ChatGoogleGenerativeAI)
    assert model.model == settings.gemini_model


# 제한 시간 전달 테스트
# 설정의 요청 제한 시간이 모델 객체에 전달되는지 확인하는 함수
def test_timeout_passed_to_model() -> None:
    # 제한 시간을 바꾼 설정
    settings = Settings(
        _env_file=None, gemini_api_key="dummy-test-key", gemini_timeout_seconds=12.5
    )
    # 모델 생성 (네트워크 호출 없음)
    model = create_chat_model(settings)
    # 제한 시간과 재시도 횟수 확인
    assert isinstance(model, ChatGoogleGenerativeAI)
    assert model.timeout == 12.5
    assert model.max_retries == 2
