from fastapi import APIRouter

from app.schemas.health import HealthResponse

# 헬스 체크 라우터 생성
router = APIRouter()


# 헬스 체크
# 서버가 정상 동작 중인지 확인해 상태 값을 반환하는 함수
@router.get("/api/health")
def get_health() -> HealthResponse:
    # 정상 상태 응답 생성 후 반환
    return HealthResponse(status="ok")
