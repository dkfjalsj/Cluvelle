from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.cases import router as cases_router
from app.api.health import router as health_router
from app.api.investigations import router as investigations_router
from app.config import get_settings


# 요청 검증 오류 응답
# 요청 본문·인자 검증 실패를 {"detail": {"code", "message"}} 형식의 422 응답으로 바꾸는 함수
async def handle_validation_error(
    request: Request, error: RequestValidationError
) -> JSONResponse:
    # 오류마다 "위치: 원인" 요약
    parts = []
    for item in error.errors():
        location = ".".join(str(part) for part in item.get("loc", ()))
        parts.append(f"{location}: {item.get('msg', '')}")
    # 정해진 형식으로 응답
    message = "요청 형식이 올바르지 않습니다: " + "; ".join(parts)
    return JSONResponse(
        status_code=422,
        content={"detail": {"code": "invalid_request", "message": message}},
    )


# 앱 생성
# 설정을 읽어 CORS·라우터·검증 오류 응답을 등록한 FastAPI 앱을 만드는 함수
def create_app() -> FastAPI:
    # 환경변수 설정 로드
    settings = get_settings()
    # FastAPI 앱 생성
    app = FastAPI(title="Cluvelle API")
    # 설정된 Origin만 허용하는 CORS 등록 (와일드카드 사용 안 함, SSE 이어 받기 헤더 허용)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Last-Event-ID"],
    )
    # 요청 검증 오류를 정해진 형식으로 응답
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    # 헬스 체크·사건·수사 라우터 등록
    app.include_router(health_router)
    app.include_router(cases_router)
    app.include_router(investigations_router)
    # 완성된 앱 반환
    return app


# uvicorn이 불러갈 앱 인스턴스
app = create_app()
