import threading
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone

from fastapi import Request

# 한국 시간 (한국은 서머타임이 없어 UTC+9 고정 오프셋과 같다)
KST = timezone(timedelta(hours=9), "Asia/Seoul")

# 제한 초과 코드별 안내 문구
LIMIT_MESSAGES = {
    "busy": "다른 수사가 진행 중입니다. 잠시 후 다시 시도해 주세요.",
    "daily_limit": "오늘 서버 전체 수사 횟수를 모두 사용했습니다. 내일 다시 시도해 주세요.",
    "ip_daily_limit": "오늘 이 접속 환경의 수사 횟수를 모두 사용했습니다. 내일 다시 시도해 주세요.",
}


# 현재 시각
# 한국 시간 기준 현재 시각을 반환하는 함수
def now_kst() -> datetime:
    # 한국 시간 현재 시각 반환
    return datetime.now(KST)


# 실행 제한 초과 예외
# 수사 시작이 실행 제한에 걸렸을 때 코드와 안내 문구를 담아 발생시키는 예외 클래스
class RateLimitExceeded(Exception):
    # 예외 생성
    # 제한 코드와 그에 맞는 안내 문구를 보관하는 함수
    def __init__(self, code: str) -> None:
        # 안내 문구
        message = LIMIT_MESSAGES[code]
        super().__init__(message)
        # 제한 코드
        self.code = code
        # 안내 문구
        self.message = message


# 실행 제한기
# 동시 실행·서버 전체 일일·IP 일일 수사 횟수를 한국 시간 0시 기준으로 관리하는 클래스
class RateLimiter:
    # 제한기 생성
    # 세 가지 상한과 현재 시각 함수를 받아 초기화하는 함수
    def __init__(
        self,
        max_concurrent_runs: int,
        daily_runs_total: int,
        daily_runs_per_ip: int,
        now: Callable[[], datetime] = now_kst,
    ) -> None:
        # 상한 값
        self.max_concurrent_runs = max_concurrent_runs
        self.daily_runs_total = daily_runs_total
        self.daily_runs_per_ip = daily_runs_per_ip
        # 현재 시각 함수 (테스트에서 주입)
        self.now = now
        # 확인·시작·기록을 한 번에 묶는 잠금
        self.lock = threading.Lock()
        # 횟수를 세는 날짜와 횟수
        self._day: date | None = None
        self._total = 0
        self._per_ip: dict[str, int] = {}

    # 제한 확인
    # 동시 실행 → 전체 일일 → IP 일일 순서로 확인해 초과하면 예외를 내는 함수 (횟수는 세지 않음)
    def check(self, client_ip: str, active_runs: int) -> None:
        # 날짜가 바뀌었으면 초기화
        self._roll_day()
        # 동시 실행 상한
        if active_runs >= self.max_concurrent_runs:
            raise RateLimitExceeded("busy")
        # 서버 전체 일일 상한
        if self._total >= self.daily_runs_total:
            raise RateLimitExceeded("daily_limit")
        # IP 일일 상한
        if self._per_ip.get(client_ip, 0) >= self.daily_runs_per_ip:
            raise RateLimitExceeded("ip_daily_limit")

    # 시작 기록
    # 수사가 실제로 시작되었을 때 전체·IP 일일 횟수를 1씩 늘리는 함수
    def record(self, client_ip: str) -> None:
        # 날짜가 바뀌었으면 초기화
        self._roll_day()
        # 횟수 증가
        self._total += 1
        self._per_ip[client_ip] = self._per_ip.get(client_ip, 0) + 1

    # 날짜 갱신
    # 한국 시간 날짜가 바뀌었으면 일일 횟수를 0으로 되돌리는 함수
    def _roll_day(self) -> None:
        # 현재 한국 시간 날짜
        today = self.now().astimezone(KST).date()
        # 날짜가 다르면 초기화
        if today != self._day:
            self._day = today
            self._total = 0
            self._per_ip = {}


# 접속 IP 조회
# X-Forwarded-For의 첫 값(앞뒤 공백 제거), 없으면 연결 주소를 접속 IP로 반환하는 함수
def get_client_ip(request: Request) -> str:
    # 프록시가 넘긴 원래 주소 목록
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # 첫 값의 앞뒤 공백 제거
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    # 없으면 연결 주소
    return request.client.host if request.client else "unknown"
