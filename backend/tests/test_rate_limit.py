from datetime import UTC, datetime
from typing import Any

import pytest
from api_helpers import api_client, blocking_runner, wait_finished

from app.services.investigation_runs import InvestigationRunStore
from app.services.rate_limit import KST, RateLimiter, RateLimitExceeded


# 고정 시각 함수 생성
# 바꿀 수 있는 현재 시각을 담은 목록과 그 시각을 돌려주는 함수를 만드는 함수
def mutable_clock(start: datetime) -> tuple[list[datetime], Any]:
    # 현재 시각 저장소
    current = [start]
    # 저장된 시각 반환 함수
    return current, lambda: current[0]


# 한국 시간 0시 초기화 테스트
# 한국 시간 날짜가 바뀌면 일일 횟수가 초기화되는지 확인하는 함수 (UTC 기준 15시가 경계)
def test_daily_reset_at_kst_midnight() -> None:
    # 한국 시간 23:59 (UTC 14:59)
    current, now = mutable_clock(datetime(2026, 11, 26, 14, 59, tzinfo=UTC))
    limiter = RateLimiter(5, daily_runs_total=1, daily_runs_per_ip=1, now=now)  # type: ignore[arg-type]
    # 1회 기록 후 같은 날에는 초과
    limiter.check("1.1.1.1", 0)
    limiter.record("1.1.1.1")
    with pytest.raises(RateLimitExceeded) as error_info:
        limiter.check("1.1.1.1", 0)
    assert error_info.value.code == "daily_limit"
    # 한국 시간 다음 날 0시 (UTC 15:00)가 되면 초기화
    current[0] = datetime(2026, 11, 26, 15, 0, tzinfo=UTC)
    limiter.check("1.1.1.1", 0)
    # 한국 시간 기준 날짜 확인
    assert current[0].astimezone(KST).day == 27


# 검사 순서 테스트
# 동시 실행 → 전체 일일 → IP 일일 순서로 검사하는지 확인하는 함수
def test_check_order() -> None:
    # 모든 상한이 이미 찬 상태
    limiter = RateLimiter(1, daily_runs_total=1, daily_runs_per_ip=1)
    limiter.record("1.1.1.1")
    # 동시 실행이 먼저
    with pytest.raises(RateLimitExceeded) as busy:
        limiter.check("1.1.1.1", 1)
    assert busy.value.code == "busy"
    # 그다음 전체 일일
    with pytest.raises(RateLimitExceeded) as total:
        limiter.check("1.1.1.1", 0)
    assert total.value.code == "daily_limit"


# 동시 실행 제한 API 테스트
# 진행 중인 수사가 있으면 429 busy로 거부되는지 확인하는 함수
def test_busy_429() -> None:
    # 멈춘 실행 하나가 진행 중인 상태
    runner, release = blocking_runner()
    store = InvestigationRunStore(runner=runner)
    limiter = RateLimiter(1, daily_runs_total=10, daily_runs_per_ip=10)
    with api_client(store=store, limiter=limiter) as client:
        first = client.post("/api/investigations", json={"case_id": "CASE-001"})
        second = client.post("/api/investigations", json={"case_id": "CASE-001"})
        release.set()
        run = store.get(first.json()["investigation_id"])
        assert run is not None
        wait_finished(run)
    # 두 번째는 busy
    assert first.status_code == 201
    assert second.status_code == 429
    assert second.json()["detail"]["code"] == "busy"
    assert second.json()["detail"]["message"]


# 전체 일일 제한 API 테스트
# 서버 전체 하루 횟수를 넘으면 429 daily_limit로 거부되는지 확인하는 함수
def test_daily_total_429() -> None:
    limiter = RateLimiter(10, daily_runs_total=1, daily_runs_per_ip=10)
    with api_client(limiter=limiter) as client:
        first = client.post("/api/investigations", json={"case_id": "CASE-001"})
        second = client.post(
            "/api/investigations",
            json={"case_id": "CASE-001"},
            headers={"X-Forwarded-For": "9.9.9.9"},
        )
    # 두 번째는 전체 일일 초과
    assert first.status_code == 201
    assert second.status_code == 429
    assert second.json()["detail"]["code"] == "daily_limit"


# IP 일일 제한·X-Forwarded-For 테스트
# X-Forwarded-For 첫 값 기준으로 IP 하루 횟수를 세고 넘으면 429 ip_daily_limit인지 확인하는 함수
def test_ip_daily_limit_uses_first_forwarded_value() -> None:
    limiter = RateLimiter(10, daily_runs_total=10, daily_runs_per_ip=1)
    with api_client(limiter=limiter) as client:
        # 첫 값 1.1.1.1
        first = client.post(
            "/api/investigations",
            json={"case_id": "CASE-001"},
            headers={"X-Forwarded-For": "1.1.1.1, 9.9.9.9"},
        )
        # 첫 값이 같은 1.1.1.1 (공백 포함, 뒤 값은 다름)
        same = client.post(
            "/api/investigations",
            json={"case_id": "CASE-001"},
            headers={"X-Forwarded-For": " 1.1.1.1 , 8.8.8.8"},
        )
        # 첫 값이 다른 2.2.2.2
        other = client.post(
            "/api/investigations",
            json={"case_id": "CASE-001"},
            headers={"X-Forwarded-For": "2.2.2.2, 1.1.1.1"},
        )
    # 같은 첫 값은 초과, 다른 첫 값은 허용
    assert first.status_code == 201
    assert same.status_code == 429
    assert same.json()["detail"]["code"] == "ip_daily_limit"
    assert other.status_code == 201
