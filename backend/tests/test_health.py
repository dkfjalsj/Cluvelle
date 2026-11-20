from fastapi.testclient import TestClient

from app.main import app

# 테스트용 HTTP 클라이언트 생성
client = TestClient(app)


# 헬스 체크 테스트
# GET /api/health가 200과 정상 상태 값을 반환하는지 확인하는 함수
def test_get_health_returns_ok() -> None:
    # 헬스 체크 API 호출
    response = client.get("/api/health")
    # 상태 코드 200 확인
    assert response.status_code == 200
    # 응답 본문이 정상 상태인지 확인
    assert response.json() == {"status": "ok"}
