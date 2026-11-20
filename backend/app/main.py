from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.config import get_settings


# 앱 생성
# 설정을 읽어 CORS와 라우터를 등록한 FastAPI 앱을 만드는 함수
def create_app() -> FastAPI:
    # 환경변수 설정 로드
    settings = get_settings()
    # FastAPI 앱 생성
    app = FastAPI(title="Cluvelle API")
    # 설정된 Origin만 허용하는 CORS 등록 (와일드카드 사용 안 함)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    # 헬스 체크 라우터 등록
    app.include_router(health_router)
    # 완성된 앱 반환
    return app


# uvicorn이 불러갈 앱 인스턴스
app = create_app()
