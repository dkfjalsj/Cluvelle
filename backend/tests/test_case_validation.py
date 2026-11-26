import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from app.schemas.answer import AnswerKey, SolutionStep
from app.schemas.case import CaseFile
from app.services.answer_key import DEFAULT_ANSWERS_DIR, load_answer_key
from app.services.case_repository import DEFAULT_CASES_DIR, CaseRepository
from app.services.case_validation import (
    ValidationReport,
    validate_all,
    validate_case,
)

# 검증 대상 사건 ID
CASE_ID = "CASE-001"
# backend 폴더와 검증 스크립트 경로
BACKEND_DIR = Path(__file__).resolve().parents[1]
SCRIPT_PATH = BACKEND_DIR.parent / "evaluation" / "validate_cases.py"


# 사건 픽스처
# 기본 경로에서 CASE-001 사건을 로드해 반환하는 함수
@pytest.fixture
def case() -> CaseFile:
    # 기본 사건 폴더에서 로드
    return CaseRepository().load_case(CASE_ID)


# 정답 픽스처
# 기본 경로에서 CASE-001 정답을 로드해 반환하는 함수
@pytest.fixture
def answer() -> AnswerKey:
    # 기본 정답 폴더에서 로드
    return load_answer_key(CASE_ID)


# 경로 단계 생성
# 도구와 인자로 해결 경로 단계를 만드는 함수
def path_step(tool: Any, **args: Any) -> SolutionStep:
    # 해결 경로 단계 반환
    return SolutionStep(tool=tool, args=args)


# 오류 문장 포함 확인
# 검증 결과 오류 중 주어진 문구가 들어간 것이 있는지 확인하는 함수
def assert_error(report: ValidationReport, text: str) -> None:
    # 실패 상태이고 해당 문구 포함
    assert not report.passed
    assert any(text in error for error in report.errors), report.errors


# 전체 사건 통과 테스트
# 기본 경로의 모든 사건이 검증을 통과하는지 확인하는 함수 (사건이 추가되면 자동 검사)
def test_all_cases_pass() -> None:
    # 전체 검증
    reports = validate_all()
    assert reports
    # 모든 사건 통과
    for report in reports:
        assert report.passed, (report.case_id, report.errors)


# CASE-001 통계 테스트
# CASE-001의 조합·증거·정답 구성 통계가 설계값과 같은지 확인하는 함수
def test_case_001_stats(case: CaseFile, answer: AnswerKey) -> None:
    # 검증 실행
    report = validate_case(case, answer)
    stats = report.stats
    assert stats is not None
    # 설계값 확인
    assert stats.combo_count == 30
    assert stats.combos_with_evidence == 22
    assert stats.combos_without_evidence == 8
    assert stats.decisive_count == 3
    assert stats.misleading_count == 2
    assert stats.path_length == 5


# 용의자 수 위반 테스트
# 용의자가 2명이면 용의자 수 오류가 나는지 확인하는 함수
def test_suspect_count(case: CaseFile, answer: AnswerKey) -> None:
    # 용의자 2명으로 바꾼 객체 (검증 우회 복사)
    broken = case.model_copy(update={"suspects": case.suspects[:2]})
    assert_error(validate_case(broken, answer), "용의자는 3명")


# 해결 경로 길이 위반 테스트
# 해결 경로가 4단계·7단계면 길이 오류가 나는지 확인하는 함수
@pytest.mark.parametrize("length", [4, 7])
def test_path_length(case: CaseFile, answer: AnswerKey, length: int) -> None:
    # 기존 경로를 자르거나 서로 다른 조사로 늘림
    steps = list(answer.solution_path)
    extra = [
        path_step("verify_alibi", suspect_id="S1"),
        path_step("verify_alibi", suspect_id="S2"),
    ]
    steps = (
        steps[:length] if length < len(steps) else steps + extra[: length - len(steps)]
    )
    broken = answer.model_copy(update={"solution_path": steps})
    assert_error(validate_case(case, broken), "해결 경로는 5~6단계")


# 교차 검증 순서 위반 테스트
# 증거를 확보하기 전에 교차 검증을 배치하면 오류가 나는지 확인하는 함수
def test_cross_check_before_collection(case: CaseFile, answer: AnswerKey) -> None:
    # 마지막 교차 검증 단계를 맨 앞으로 이동
    steps = list(answer.solution_path)
    steps = [steps[-1], *steps[:-1]]
    broken = answer.model_copy(update={"solution_path": steps})
    assert_error(validate_case(case, broken), "아직 확보하지 않은 증거")


# 결정적 증거 미확보 테스트
# C3 22:00-23:00 단계를 다른 조회로 바꾸면 확보하지 못한 결정적 증거 오류가 나는지 확인하는 함수
def test_decisive_not_collected(case: CaseFile, answer: AnswerKey) -> None:
    # 3단계를 로비 카메라 조회로 교체하고 교차 검증도 확보 가능한 증거로 교체
    steps = list(answer.solution_path)
    steps[2] = path_step("check_cctv", camera_id="C1", time_window="20:00-21:00")
    steps[4] = path_step("cross_check_evidence", evidence_ids=["E9", "E13"])
    broken = answer.model_copy(update={"solution_path": steps})
    report = validate_case(case, broken)
    assert_error(report, "확보하지 못한 결정적 증거가 있습니다: E19")


# 같은 단계 반복 테스트
# 해결 경로에 같은 조사가 두 번 있으면 반복 오류가 나는지 확인하는 함수
def test_repeated_step(case: CaseFile, answer: AnswerKey) -> None:
    # 1단계를 한 번 더 추가 (6단계)
    steps = [*answer.solution_path, answer.solution_path[0]]
    broken = answer.model_copy(update={"solution_path": steps})
    assert_error(validate_case(case, broken), "6단계가 1단계와 같은 조사를 반복")


# 결정적 증거 집중 테스트
# 같은 조회 위치에 결정적 증거가 2개 있으면 오류가 나는지 확인하는 함수
def test_decisive_concentration(case: CaseFile, answer: AnswerKey) -> None:
    # E18의 시간대를 E19와 같은 22:00-23:00으로 옮긴 사건
    data = case.model_dump()
    for item in data["evidence"]:
        if item["id"] == "E18":
            item["locator"]["time_window"] = "22:00-23:00"
    moved = CaseFile.model_validate(data)
    # 결정적 증거에 E18 추가 (검증 우회 복사)
    broken = answer.model_copy(update={"decisive_evidence_ids": ["E1", "E19", "E18"]})
    assert_error(
        validate_case(moved, broken), "같은 조회 위치(check_cctv C3 22:00-23:00)"
    )


# 결론 문구 금지 테스트
# 증거 요약에 금지 단어가 있으면 증거 ID와 단어를 담은 오류가 나는지 확인하는 함수
def test_forbidden_summary_word(case: CaseFile, answer: AnswerKey) -> None:
    # E5 요약에 금지 단어 추가
    data = case.model_dump()
    for item in data["evidence"]:
        if item["id"] == "E5":
            item["summary"] += " 그가 범인이다."
    broken = CaseFile.model_validate(data)
    assert_error(validate_case(broken, answer), "증거 E5의 요약에 결론 문구 '범인'")


# 폴더 복사
# CASE-001 사건·정답 파일을 임시 폴더로 복사해 (사건 폴더, 정답 폴더)를 반환하는 함수
def copy_case_001(tmp_path: Path) -> tuple[Path, Path]:
    # 임시 사건·정답 폴더 생성
    cases_dir = tmp_path / "cases"
    answers_dir = tmp_path / "answers"
    cases_dir.mkdir()
    answers_dir.mkdir()
    # 원본 파일 복사 (원본은 수정하지 않음)
    shutil.copy(DEFAULT_CASES_DIR / f"{CASE_ID}.json", cases_dir)
    shutil.copy(DEFAULT_ANSWERS_DIR / f"{CASE_ID}.json", answers_dir)
    return cases_dir, answers_dir


# 정답 파일 없음 테스트
# 사건 파일에 맞는 정답 파일이 없으면 그 사건이 오류로 보고되는지 확인하는 함수
def test_missing_answer_file(tmp_path: Path) -> None:
    # 정답 파일 삭제
    cases_dir, answers_dir = copy_case_001(tmp_path)
    (answers_dir / f"{CASE_ID}.json").unlink()
    reports = validate_all(cases_dir, answers_dir)
    # 사건 하나가 정답 없음 오류
    assert len(reports) == 1
    assert_error(reports[0], "정답 파일이 없습니다")
    assert reports[0].stats is None


# 사건 없는 정답 파일 테스트
# 사건 파일이 없는 정답 파일이 오류로 보고되는지 확인하는 함수
def test_orphan_answer_file(tmp_path: Path) -> None:
    # 다른 ID의 정답 파일 추가
    cases_dir, answers_dir = copy_case_001(tmp_path)
    data = json.loads((answers_dir / f"{CASE_ID}.json").read_text(encoding="utf-8"))
    data["case_id"] = "CASE-777"
    (answers_dir / "CASE-777.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )
    reports = validate_all(cases_dir, answers_dir)
    # CASE-001은 통과, CASE-777은 사건 없음 오류
    by_id = {report.case_id: report for report in reports}
    assert by_id[CASE_ID].passed
    assert_error(by_id["CASE-777"], "사건 파일이 없는 정답 파일")


# 스크립트 실행
# 검증 스크립트를 backend 폴더에서 하위 프로세스로 실행해 결과를 반환하는 함수
def run_script(*args: str) -> subprocess.CompletedProcess[str]:
    # 한글 출력이 깨지지 않도록 UTF-8 지정
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
    )


# 스크립트 전체 실행 테스트
# 스크립트가 종료 코드 0과 정해진 마지막 줄 형식으로 끝나는지 확인하는 함수
def test_script_all_cases() -> None:
    # 전체 검증 실행
    result = run_script()
    assert result.returncode == 0, result.stdout + result.stderr
    # 마지막 줄 형식 확인
    last_line = result.stdout.strip().splitlines()[-1]
    count = len(validate_all())
    assert last_line == f"전체 {count}건 중 통과 {count}건, 실패 0건"
    assert "[CASE-001] 통과" in result.stdout


# 스크립트 잘못된 인자 테스트
# 형식이 틀리거나 없는 사건 ID를 주면 종료 코드 2인지 확인하는 함수
@pytest.mark.parametrize("case_id", ["case-1", "CASE-998"])
def test_script_bad_case_id(case_id: str) -> None:
    # 잘못된 ID로 실행
    result = run_script(case_id)
    assert result.returncode == 2
    assert result.stdout.strip().startswith("오류:")
