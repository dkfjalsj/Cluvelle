"""사건 검증 스크립트.

backend 폴더에서 실행한다: uv run python ../evaluation/validate_cases.py [CASE-001]
인자가 없으면 전체 사건을, 사건 ID를 주면 그 사건만 검사한다.
"""

import re
import sys
from pathlib import Path

# backend 폴더를 import 경로에 추가 (검증 로직은 backend 모듈을 그대로 사용)
BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.schemas.case import CASE_ID_PATTERN
from app.services.case_repository import DEFAULT_CASES_DIR
from app.services.case_validation import (
    ValidationReport,
    validate_all,
    validate_case_files,
)

# 종료 코드
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_BAD_ARGUMENT = 2


# 실행 진입점
# 인자에 따라 전체 또는 한 사건을 검증해 결과를 출력하고 종료 코드를 반환하는 함수
def main(argv: list[str] | None = None) -> int:
    # 명령줄 인자 (없으면 실제 명령줄 사용)
    args = sys.argv[1:] if argv is None else argv
    # 인자가 둘 이상이면 사용법 안내
    if len(args) > 1:
        print("사용법: uv run python ../evaluation/validate_cases.py [CASE-001]")
        return EXIT_BAD_ARGUMENT

    # 사건 ID가 있으면 그 사건만 검사
    if args:
        case_id = args[0]
        # 형식이 틀리면 오류
        if re.fullmatch(CASE_ID_PATTERN, case_id) is None:
            print(f"오류: 사건 ID 형식이 올바르지 않습니다: {case_id}")
            return EXIT_BAD_ARGUMENT
        # 사건 파일이 없으면 오류
        if not (DEFAULT_CASES_DIR / f"{case_id}.json").is_file():
            print(f"오류: 사건 파일이 없습니다: {case_id}")
            return EXIT_BAD_ARGUMENT
        reports = [validate_case_files(case_id)]
    else:
        # 전체 사건 검사 (사건 없는 정답 파일 포함)
        reports = validate_all()

    # 사건마다 결과 출력
    for report in reports:
        print_report(report)
    # 요약 줄
    passed = sum(report.passed for report in reports)
    failed = len(reports) - passed
    print(f"전체 {len(reports)}건 중 통과 {passed}건, 실패 {failed}건")
    # 실패가 있으면 1, 아니면 0
    return EXIT_FAILED if failed else EXIT_OK


# 검증 결과 출력
# 사건 하나의 통과 여부·오류·통계·사람 검토 항목을 정해진 형식으로 출력하는 함수
def print_report(report: ValidationReport) -> None:
    # 제목 줄
    print(f"[{report.case_id}] {'통과' if report.passed else '실패'}")
    # 실패면 오류 줄 먼저
    for error in report.errors:
        print(f"  오류: {error}")
    # 통계가 없으면(불러오기 실패) 여기서 끝
    stats = report.stats
    if stats is None:
        return
    # 통계 줄
    print(
        f"  조합 {stats.combo_count} "
        f"(증거 있음 {stats.combos_with_evidence} / 없음 {stats.combos_without_evidence})"
        f" · 결정적 {stats.decisive_count} · 오해 {stats.misleading_count}"
        f" · 해결 경로 {stats.path_length}"
    )
    # 사람 검토 항목
    print("  사람 검토:")
    for item in report.review_items:
        print(f"    {item}")


# 모듈 직접 실행 시 진입점 호출
if __name__ == "__main__":
    sys.exit(main())
