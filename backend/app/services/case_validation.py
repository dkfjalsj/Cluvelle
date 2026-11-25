"""사건 데이터 검증.

사건 설계 규칙(용의자 수, 조합 수, 정답 구성, 해결 경로 실행, 결정적 증거 분산, 결론 문구 금지)을
결정적으로 검사한다. 평가·CI 전용이며 정답 파일을 읽는다.
"""

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.schemas.answer import AnswerKey
from app.schemas.case import CASE_ID_PATTERN, CaseFile, Evidence
from app.schemas.tool import InvestigationResult
from app.services.answer_key import (
    DEFAULT_ANSWERS_DIR,
    load_answer_key,
    validate_answer_against_case,
)
from app.services.case_repository import (
    DEFAULT_CASES_DIR,
    CaseDataError,
    CaseNotFoundError,
    CaseRepository,
    InvalidCaseIdError,
)
from app.tools import (
    ToolArgumentError,
    check_cctv,
    cross_check_evidence,
    inspect_scene,
    interview_suspect,
    verify_alibi,
)

# 도구 이름 → 도구 함수 (해결 경로 실행용)
TOOL_FUNCTIONS: dict[str, Callable[..., BaseModel]] = {
    "inspect_scene": inspect_scene,
    "interview_suspect": interview_suspect,
    "check_cctv": check_cctv,
    "verify_alibi": verify_alibi,
    "cross_check_evidence": cross_check_evidence,
}

# 규칙 범위
SUSPECT_COUNT = 3
COMBO_RANGE = (25, 35)
DECISIVE_RANGE = (2, 3)
MISLEADING_RANGE = (1, 2)
PATH_RANGE = (5, 6)
# 증거 요약에 쓰면 안 되는 결론 단어
FORBIDDEN_SUMMARY_WORDS = ("범인", "범행", "훔친", "도둑", "유죄")
# locator 필드 표기 순서
LOCATOR_FIELD_ORDER = (
    "location_id",
    "suspect_id",
    "topic_id",
    "camera_id",
    "time_window",
)


# 사건 통계
# 조합 수·증거 있는 조합 수·결과 없는 조합 수·정답 구성 수를 담는 클래스
class CaseStats(BaseModel):
    # 조사 가능 조합 수
    combo_count: int
    # 증거가 있는 조합 수
    combos_with_evidence: int
    # 결과 없는 조합 수
    combos_without_evidence: int
    # 결정적 증거 수
    decisive_count: int
    # 오해 유발 증거 수
    misleading_count: int
    # 해결 경로 길이
    path_length: int


# 검증 결과
# 사건 하나의 오류·통계·사람 검토 항목을 담는 클래스
class ValidationReport(BaseModel):
    # 사건 ID
    case_id: str
    # 규칙 위반 오류 목록
    errors: list[str]
    # 통계 (사건·정답을 불러오지 못하면 None)
    stats: CaseStats | None
    # 사람 검토 항목
    review_items: list[str]

    # 통과 여부
    # 오류가 하나도 없으면 True를 반환하는 함수
    @property
    def passed(self) -> bool:
        # 오류 목록이 비었는지 반환
        return not self.errors


# 사건 검증
# 사건과 정답을 받아 설계 규칙 7가지를 검사하고 통계·검토 항목과 함께 결과를 반환하는 함수
def validate_case(case: CaseFile, answer: AnswerKey) -> ValidationReport:
    # 오류 목록
    errors: list[str] = []

    # 1. 용의자 수
    if len(case.suspects) != SUSPECT_COUNT:
        errors.append(
            f"용의자는 {SUSPECT_COUNT}명이어야 합니다: {len(case.suspects)}명"
        )

    # 2. 조사 가능 조합 수
    combo_count = _combo_count(case)
    if not COMBO_RANGE[0] <= combo_count <= COMBO_RANGE[1]:
        errors.append(
            f"조사 가능 조합 수는 {COMBO_RANGE[0]}~{COMBO_RANGE[1]}개여야 합니다: "
            f"{combo_count}개"
        )

    # 3. 결정적·오해 유발 증거 수
    decisive_count = len(answer.decisive_evidence_ids)
    misleading_count = len(answer.misleading_evidence_ids)
    if not DECISIVE_RANGE[0] <= decisive_count <= DECISIVE_RANGE[1]:
        errors.append(
            f"결정적 증거는 {DECISIVE_RANGE[0]}~{DECISIVE_RANGE[1]}개여야 합니다: "
            f"{decisive_count}개"
        )
    if not MISLEADING_RANGE[0] <= misleading_count <= MISLEADING_RANGE[1]:
        errors.append(
            f"오해 유발 증거는 {MISLEADING_RANGE[0]}~{MISLEADING_RANGE[1]}개여야 합니다: "
            f"{misleading_count}개"
        )

    # 4. 해결 경로 길이
    path_length = len(answer.solution_path)
    if not PATH_RANGE[0] <= path_length <= PATH_RANGE[1]:
        errors.append(
            f"해결 경로는 {PATH_RANGE[0]}~{PATH_RANGE[1]}단계여야 합니다: {path_length}단계"
        )

    # 5. 해결 경로 실제 실행
    path_errors, path_items = _run_solution_path(case, answer)
    errors.extend(path_errors)

    # 6. 한 위치 결정적 증거 집중 금지
    errors.extend(_check_decisive_concentration(case, answer))

    # 7. 결론 문구 금지
    for item in case.evidence:
        for word in FORBIDDEN_SUMMARY_WORDS:
            if word in item.summary:
                errors.append(f"증거 {item.id}의 요약에 결론 문구 '{word}'가 있습니다.")

    # 통계 계산
    combos_with_evidence = len({_location_key(item) for item in case.evidence})
    stats = CaseStats(
        combo_count=combo_count,
        combos_with_evidence=combos_with_evidence,
        combos_without_evidence=combo_count - combos_with_evidence,
        decisive_count=decisive_count,
        misleading_count=misleading_count,
        path_length=path_length,
    )
    # 사람 검토 항목 (결정적 → 오해 유발 → 경로 단계)
    review_items = [
        *_evidence_review_items("결정적", answer.decisive_evidence_ids, case),
        *_evidence_review_items("오해", answer.misleading_evidence_ids, case),
        *path_items,
    ]
    # 결과 반환
    return ValidationReport(
        case_id=case.case_id, errors=errors, stats=stats, review_items=review_items
    )


# 전체 사건 검증
# 사건 폴더의 모든 사건과 정답을 검사하고 사건 없는 정답 파일도 오류로 보고하는 함수
def validate_all(
    cases_dir: Path = DEFAULT_CASES_DIR,
    answers_dir: Path = DEFAULT_ANSWERS_DIR,
) -> list[ValidationReport]:
    # 사건 ID 목록
    case_ids = CaseRepository(cases_dir).list_case_ids()
    # 사건마다 검사
    reports = [
        validate_case_files(case_id, cases_dir, answers_dir) for case_id in case_ids
    ]
    # 사건 파일이 없는 정답 파일을 오류로 보고
    for answer_id in _list_answer_ids(answers_dir):
        if answer_id not in case_ids:
            reports.append(
                ValidationReport(
                    case_id=answer_id,
                    errors=[f"사건 파일이 없는 정답 파일입니다: {answer_id}.json"],
                    stats=None,
                    review_items=[],
                )
            )
    # 결과 목록 반환
    return reports


# 사건 하나 파일 검증
# 사건·정답 파일을 불러와 대조한 뒤 규칙을 검사하고, 불러오기 실패는 오류로 기록해 반환하는 함수
def validate_case_files(
    case_id: str,
    cases_dir: Path = DEFAULT_CASES_DIR,
    answers_dir: Path = DEFAULT_ANSWERS_DIR,
) -> ValidationReport:
    # 불러오기 실패 결과 생성
    # 오류 문장 하나만 담고 통계가 없는 검증 결과를 만드는 함수
    def failed(message: str) -> ValidationReport:
        # 오류 하나짜리 결과 반환
        return ValidationReport(
            case_id=case_id, errors=[message], stats=None, review_items=[]
        )

    # 사건 로드 (형식·파일·스키마 오류는 그 사건의 오류)
    try:
        case = CaseRepository(cases_dir).load_case(case_id)
    except (InvalidCaseIdError, CaseNotFoundError, CaseDataError) as error:
        return failed(f"사건을 불러오지 못했습니다: {error}")
    # 정답 파일이 없으면 오류
    if not (answers_dir / f"{case_id}.json").is_file():
        return failed(f"정답 파일이 없습니다: {case_id}.json")
    # 정답 로드
    try:
        answer = load_answer_key(case_id, answers_dir)
    except (InvalidCaseIdError, CaseNotFoundError, CaseDataError) as error:
        return failed(f"정답을 불러오지 못했습니다: {error}")
    # 정답과 사건 대조
    try:
        validate_answer_against_case(answer, case)
    except CaseDataError as error:
        return failed(f"정답과 사건이 맞지 않습니다: {error}")
    # 규칙 검사
    return validate_case(case, answer)


# 해결 경로 실행
# 해결 경로를 도구로 순서대로 실행해 경로 오류 목록과 단계별 검토 항목을 반환하는 함수
def _run_solution_path(
    case: CaseFile, answer: AnswerKey
) -> tuple[list[str], list[str]]:
    # 오류·검토 항목·확보 증거·처음 나온 단계 번호
    errors: list[str] = []
    items: list[str] = []
    collected: set[str] = set()
    first_steps: dict[tuple[str, tuple[Any, ...]], int] = {}

    # 단계를 순서대로 실행
    for number, step in enumerate(answer.solution_path, start=1):
        # 이번 단계에서 반환된 증거
        returned: list[str] = []
        # 같은 단계 반복 확인 (교차 검증은 증거 집합 기준)
        key = _step_key(step.tool, step.args)
        if key in first_steps:
            errors.append(
                f"해결 경로 {number}단계가 {first_steps[key]}단계와 같은 조사를 반복합니다."
            )
        else:
            first_steps[key] = number
            # 교차 검증은 앞 단계에서 확보한 증거만 허용
            missing: list[str] = []
            if step.tool == "cross_check_evidence":
                evidence_ids = step.args.get("evidence_ids", [])
                ids = evidence_ids if isinstance(evidence_ids, list) else [evidence_ids]
                missing = [item for item in ids if item not in collected]
            if missing:
                errors.append(
                    f"해결 경로 {number}단계 교차 검증에 아직 확보하지 않은 증거가 있습니다: "
                    f"{', '.join(missing)}"
                )
            else:
                # 도구 실행 (인자 오류면 실행 실패)
                try:
                    result = TOOL_FUNCTIONS[step.tool](case, **step.args)
                except (ToolArgumentError, TypeError) as error:
                    errors.append(f"해결 경로 {number}단계 실행 실패: {error}")
                else:
                    # 조회 도구면 반환 증거 기록
                    if isinstance(result, InvestigationResult):
                        returned = [item.id for item in result.evidence]
                        collected.update(returned)
        # 단계 검토 항목
        args_text = json.dumps(step.args, ensure_ascii=False)
        returned_text = ", ".join(returned) or "없음"
        items.append(f"[경로 {number}] {step.tool} {args_text} → 확보 {returned_text}")

    # 경로 끝까지 실행한 뒤 결정적 증거 확보 여부
    not_collected = [
        item for item in answer.decisive_evidence_ids if item not in collected
    ]
    if not_collected:
        errors.append(
            f"해결 경로로 확보하지 못한 결정적 증거가 있습니다: {', '.join(not_collected)}"
        )
    # 오류와 검토 항목 반환
    return errors, items


# 결정적 증거 집중 검사
# 같은 조회 위치에 결정적 증거가 2개 이상이면 오류 목록을 반환하는 함수
def _check_decisive_concentration(case: CaseFile, answer: AnswerKey) -> list[str]:
    # 증거 ID 조회 표
    evidence_by_id = {item.id: item for item in case.evidence}
    # 위치 → 결정적 증거 ID
    by_location: dict[tuple[str, tuple[str, ...]], list[str]] = {}
    for evidence_id in answer.decisive_evidence_ids:
        item = evidence_by_id.get(evidence_id)
        if item is None:
            continue
        by_location.setdefault(_location_key(item), []).append(evidence_id)
    # 2개 이상 모인 위치를 오류로
    return [
        f"같은 조회 위치({_format_location(location)})에 결정적 증거가 2개 이상 있습니다: "
        f"{', '.join(ids)}"
        for location, ids in by_location.items()
        if len(ids) >= 2
    ]


# 조사 가능 조합 수
# 장소 + 용의자×주제 + 카메라×시간대 + 용의자로 조합 수를 계산하는 함수
def _combo_count(case: CaseFile) -> int:
    # 공식대로 합산
    return (
        len(case.locations)
        + len(case.suspects) * len(case.topics)
        + sum(len(camera.time_windows) for camera in case.cameras)
        + len(case.suspects)
    )


# 조회 위치 키
# 증거의 도구와 locator 값(필드 순서)으로 위치 키를 만드는 함수
def _location_key(item: Evidence) -> tuple[str, tuple[str, ...]]:
    # 값이 있는 locator 필드를 정해진 순서로
    locator = item.locator.model_dump(exclude_none=True)
    values = tuple(
        str(locator[field]) for field in LOCATOR_FIELD_ORDER if field in locator
    )
    # 도구 이름과 함께 반환
    return item.source_tool, values


# 위치 표기
# 위치 키를 "도구 값1 값2" 형식 문자열로 바꾸는 함수
def _format_location(location: tuple[str, tuple[str, ...]]) -> str:
    # 도구 이름과 값을 공백으로 연결
    tool, values = location
    return " ".join([tool, *values])


# 단계 비교 키
# 해결 경로 단계의 도구와 인자로 반복 비교용 키를 만드는 함수 (교차 검증은 증거 집합)
def _step_key(tool: str, args: dict[str, Any]) -> tuple[str, tuple[Any, ...]]:
    # 교차 검증은 증거 ID 집합으로 비교
    if tool == "cross_check_evidence":
        evidence_ids = args.get("evidence_ids", [])
        ids = evidence_ids if isinstance(evidence_ids, list) else [evidence_ids]
        return tool, tuple(sorted(set(ids)))
    # 그 외는 인자 항목을 정렬해 비교
    return tool, tuple(sorted((key, str(value)) for key, value in args.items()))


# 증거 검토 항목
# 증거 ID 목록을 "[종류] ID (위치): 요약" 형식의 검토 항목으로 만드는 함수
def _evidence_review_items(
    label: str, evidence_ids: list[str], case: CaseFile
) -> list[str]:
    # 증거 ID 조회 표
    evidence_by_id = {item.id: item for item in case.evidence}
    # 항목 목록
    items: list[str] = []
    for evidence_id in evidence_ids:
        item = evidence_by_id.get(evidence_id)
        # 없는 증거는 건너뜀 (정답 대조에서 걸러짐)
        if item is None:
            continue
        location = _format_location(_location_key(item))
        items.append(f"[{label}] {evidence_id} ({location}): {item.summary}")
    # 항목 반환
    return items


# 정답 파일 ID 목록
# 정답 폴더에서 CASE-###.json 형식 파일의 사건 ID를 정렬해 반환하는 함수
def _list_answer_ids(answers_dir: Path) -> list[str]:
    # 이름이 사건 ID 형식인 JSON 파일만
    return sorted(
        path.stem
        for path in answers_dir.glob("*.json")
        if re.fullmatch(CASE_ID_PATTERN, path.stem) is not None
    )
