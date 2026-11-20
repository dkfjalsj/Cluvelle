from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


# 애플리케이션 설정
# 환경변수에서 서버 설정 값을 읽어 보관하는 클래스
class Settings(BaseSettings):
    # backend/.env를 읽되(없으면 건너뜀) OS 환경변수가 우선하고, 대소문자 구분 없이 정의되지 않은 값은 무시
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Gemini API 키 (없어도 서버 기동 가능)
    gemini_api_key: str | None = None
    # CORS 허용 Origin 목록 (콤마 구분 문자열을 직접 파싱하도록 JSON 디코딩 비활성화)
    allowed_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]

    # 허용 Origin 파싱
    # 콤마로 구분된 문자열을 공백 없는 Origin 목록으로 바꾸는 함수
    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_allowed_origins(cls, value: object) -> object:
        # 문자열이면 콤마로 나누고 빈 항목은 제외
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        # 이미 목록 등 다른 형태면 그대로 검증 단계로 전달
        return value


# 설정 객체 조회
# 설정을 한 번만 생성해 재사용하도록 캐시된 설정 객체를 반환하는 함수
@lru_cache
def get_settings() -> Settings:
    # 환경변수를 읽어 설정 객체 생성
    return Settings()
