import json

from api_helpers import api_client, blocking_runner, read_sse, wait_finished

from app.agent.llm import MissingApiKeyError
from app.services.investigation_runs import InvestigationRunStore
from app.services.rate_limit import RateLimiter

# 공개 응답에 나오면 안 되는 문자열
FORBIDDEN_TEXTS = (
    "culprit",
    "decisive",
    "solution",
    "grading_notes",
    "facts",
    "evidence",
)


# 사건 목록 테스트
# 사건 목록이 ID 순서로 정해진 필드만 담고 정답 정보가 없는지 확인하는 함수
def test_list_cases() -> None:
    with api_client() as client:
        response = client.get("/api/cases")
    # 200과 사건 ID 순서
    assert response.status_code == 200
    items = response.json()
    assert [item["case_id"] for item in items] == [f"CASE-00{n}" for n in range(1, 6)]
    # 필드 집합
    assert set(items[0]) == {"case_id", "title", "difficulty", "summary", "tool_budget"}
    # 정답 정보 없음
    text = json.dumps(items, ensure_ascii=False)
    for word in FORBIDDEN_TEXTS:
        assert word not in text


# 사건 상세 테스트
# 사건 상세가 공개 정보만 담고 형식 오류는 400, 없는 사건은 404인지 확인하는 함수
def test_get_case() -> None:
    with api_client() as client:
        ok = client.get("/api/cases/CASE-001")
        bad = client.get("/api/cases/case-1")
        missing = client.get("/api/cases/CASE-998")
    # 공개 정보에 정답·증거 없음
    assert ok.status_code == 200
    for word in FORBIDDEN_TEXTS:
        assert word not in ok.text
    # 오류 코드
    assert bad.status_code == 400
    assert bad.json() == {
        "detail": {
            "code": "invalid_case_id",
            "message": "사건 ID 형식이 올바르지 않습니다.",
        }
    }
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "case_not_found"


# 수사 전체 흐름 테스트
# 수사 시작 → 이벤트 전체 수신 → 결과에 보고서와 채점이 있는지 확인하는 함수
def test_full_flow() -> None:
    with api_client() as client:
        # 수사 시작
        start = client.post("/api/investigations", json={"case_id": "CASE-001"})
        assert start.status_code == 201
        body = start.json()
        assert set(body) == {"investigation_id", "case_id", "status"}
        run_id = body["investigation_id"]
        # 이벤트 전체 수신
        raw, events = read_sse(client, f"/api/investigations/{run_id}/events")
        # 결과 조회
        result = client.get(f"/api/investigations/{run_id}/result").json()
    # 이벤트 순서와 마지막 이벤트
    assert [event["id"] for event in events] == list(range(len(events)))
    assert events[-1]["event"] == "finished"
    assert "facts" not in raw
    # 결과: 보고서와 채점
    assert result["status"] == "completed"
    assert result["final_report"]["suspect_id"] == "S3"
    assert result["report_status"] == "accepted"
    assert result["grading"]["verdict"] == "partial_success"
    assert result["history"][0]["hypothesis"] == "아직 가설 없음"


# SSE 헤더 테스트
# SSE 응답에 정해진 헤더가 붙는지 확인하는 함수
def test_sse_headers() -> None:
    with api_client() as client:
        run_id = client.post(
            "/api/investigations", json={"case_id": "CASE-001"}
        ).json()["investigation_id"]
        with client.stream("GET", f"/api/investigations/{run_id}/events") as response:
            headers = response.headers
            "".join(response.iter_text())
    # 헤더 확인
    assert headers["content-type"].startswith("text/event-stream")
    assert headers["cache-control"] == "no-cache"
    assert headers["x-accel-buffering"] == "no"


# 종료 전 결과 테스트
# 수사가 끝나기 전 결과의 보고서·채점은 null이고 끝난 뒤에는 채워지는지 확인하는 함수
def test_result_before_finish() -> None:
    # 해제 전까지 멈추는 실행 함수
    runner, release = blocking_runner()
    store = InvestigationRunStore(runner=runner)
    with api_client(store=store) as client:
        run_id = client.post(
            "/api/investigations", json={"case_id": "CASE-001"}
        ).json()["investigation_id"]
        # 종료 전 결과
        before = client.get(f"/api/investigations/{run_id}/result").json()
        # 해제 후 종료 기다리기
        release.set()
        run = store.get(run_id)
        assert run is not None
        wait_finished(run)
        after = client.get(f"/api/investigations/{run_id}/result").json()
    # 종료 전에는 null
    assert before["status"] in ("pending", "running")
    assert before["final_report"] is None
    assert before["grading"] is None
    assert before["report_status"] is None
    assert before["validation_rejections"] is None
    # 종료 후에는 채워짐
    assert after["grading"] is not None
    assert after["final_report"] is not None


# 이어 받기 테스트
# Last-Event-ID 헤더나 last_event_id 쿼리를 주면 그 다음 번호부터 받는지 확인하는 함수
def test_resume_from_last_event_id() -> None:
    with api_client() as client:
        run_id = client.post(
            "/api/investigations", json={"case_id": "CASE-001"}
        ).json()["investigation_id"]
        url = f"/api/investigations/{run_id}/events"
        _, full = read_sse(client, url)
        _, by_header = read_sse(client, url, headers={"Last-Event-ID": "2"})
        _, by_query = read_sse(client, url, params={"last_event_id": 3})
    # 그 다음 번호부터
    assert [event["id"] for event in by_header] == [
        e["id"] for e in full if e["id"] > 2
    ]
    assert [event["id"] for event in by_query] == [e["id"] for e in full if e["id"] > 3]
    assert by_header[-1]["event"] == "finished"


# 없는 수사 테스트
# 없는 수사 ID로 이벤트·결과를 요청하면 404인지 확인하는 함수
def test_unknown_investigation() -> None:
    with api_client() as client:
        events = client.get("/api/investigations/nope/events")
        result = client.get("/api/investigations/nope/result")
    # 404와 코드
    for response in (events, result):
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "investigation_not_found"


# 요청 본문 검증 테스트
# 추가 필드·누락 필드가 있으면 422 invalid_request로 거부되는지 확인하는 함수
def test_request_body_validation() -> None:
    with api_client() as client:
        extra = client.post(
            "/api/investigations", json={"case_id": "CASE-001", "mode": "fixed"}
        )
        missing = client.post("/api/investigations", json={})
    # 정해진 형식의 422
    for response in (extra, missing):
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "invalid_request"


# 사건 오류 테스트
# 수사 시작 요청의 사건 ID가 틀리면 400·404인지 확인하는 함수
def test_start_with_bad_case() -> None:
    with api_client() as client:
        bad = client.post("/api/investigations", json={"case_id": "case-1"})
        missing = client.post("/api/investigations", json={"case_id": "CASE-998"})
    # 오류 코드
    assert bad.status_code == 400
    assert missing.status_code == 404


# API 키 없음 테스트
# 모델을 만들 수 없으면 503이고 실행 횟수에 세지 않는지 확인하는 함수
def test_missing_api_key_returns_503() -> None:
    # 키 없음 예외를 내는 모델 생성 함수
    def no_key() -> None:
        raise MissingApiKeyError("키 없음")

    # 하루 1회만 허용하는 제한기
    limiter = RateLimiter(
        max_concurrent_runs=5, daily_runs_total=1, daily_runs_per_ip=1
    )
    with api_client(limiter=limiter, model_factory=no_key) as client:  # type: ignore[arg-type]
        response = client.post("/api/investigations", json={"case_id": "CASE-001"})
    # 503과 코드
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "llm_unavailable"
    # 횟수를 세지 않았으므로 정상 시작 가능
    with api_client(limiter=limiter) as client:
        ok = client.post("/api/investigations", json={"case_id": "CASE-001"})
    assert ok.status_code == 201
