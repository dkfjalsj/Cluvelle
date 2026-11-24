from typing import Literal

from pydantic import BaseModel


# 헬스 체크 응답
# 서버 상태 값을 담아 응답하는 클래스
class HealthResponse(BaseModel):
    # 서버 상태 (정상일 때 "ok")
    status: Literal["ok"]
