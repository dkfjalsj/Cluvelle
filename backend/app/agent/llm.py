from langchain_core.language_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI

from app.config import Settings


# API 키 누락 오류
# Gemini API 키가 설정되지 않았을 때 발생시키는 예외 클래스
class MissingApiKeyError(RuntimeError):
    pass


# 채팅 모델 생성
# 설정의 API 키와 모델 이름으로 Gemini 채팅 모델을 만들어 반환하는 함수
def create_chat_model(settings: Settings) -> BaseChatModel:
    # 키가 없거나 공백만 있으면 오류
    api_key = settings.gemini_api_key
    if api_key is None or not api_key.strip():
        raise MissingApiKeyError(
            "GEMINI_API_KEY가 설정되지 않았습니다. backend/.env를 확인하세요."
        )
    # Gemini 채팅 모델 생성 (재시도 2회, 요청 제한 시간 적용, 그 외 옵션은 기본값)
    return ChatGoogleGenerativeAI(
        model=settings.gemini_model,
        api_key=api_key,
        max_retries=2,
        timeout=settings.gemini_timeout_seconds,
    )
