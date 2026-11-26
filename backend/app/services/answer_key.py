"""정답 키 로더.

평가·채점 전용 모듈이다. 사건 로더·공개 정보·조사 도구 경로에서는 이 모듈을 import하지 않는다.
"""

from pathlib import Path

from pydantic import ValidationError

from app.schemas.answer import AnswerKey
from app.schemas.case import CaseFile
from app.services.case_repository import (
    CaseDataError,
    CaseNotFoundError,
    ensure_valid_case_id,
)

# 기본 정답 폴더 경로 (backend/data/answers)
DEFAULT_ANSWERS_DIR = Path(__file__).resolve().parents[2] / "data" / "answers"


# 정답 키 로드
# 사건 ID로 정답 파일을 읽어 스키마 검증을 거친 정답 키를 반환하는 함수
def load_answer_key(case_id: str, answers_dir: Path = DEFAULT_ANSWERS_DIR) -> AnswerKey:
    # ID 형식 검사
    ensure_valid_case_id(case_id)
    # 정답 파일 경로
    path = answers_dir / f"{case_id}.json"
    # 파일이 없으면 오류
    if not path.is_file():
        raise CaseNotFoundError(f"정답 파일을 찾을 수 없습니다: {case_id}")
    # 파일 읽기 후 스키마 검증
    try:
        answer = AnswerKey.model_validate_json(path.read_text(encoding="utf-8"))
    except ValidationError as error:
        # 검증 실패 원인을 담아 오류 변환
        raise CaseDataError(
            f"정답 {case_id} 데이터가 올바르지 않습니다: {error}"
        ) from error
    # 파일 이름의 ID와 내용의 ID가 다르면 오류
    if answer.case_id != case_id:
        raise CaseDataError(
            f"파일 이름의 사건 ID({case_id})와 정답의 case_id({answer.case_id})가 다릅니다."
        )
    # 검증된 정답 반환
    return answer


# 정답과 사건 대조 검증
# 정답의 범인·증거 ID가 사건 데이터에 있고 결정적·오해 유발 증거가 겹치지 않는지 확인하는 함수
def validate_answer_against_case(answer: AnswerKey, case: CaseFile) -> None:
    # 정답과 사건의 ID가 같아야 함
    if answer.case_id != case.case_id:
        raise CaseDataError(
            f"정답의 case_id({answer.case_id})와 사건의 case_id({case.case_id})가 다릅니다."
        )
    # 범인이 용의자 목록에 있어야 함
    suspect_ids = {suspect.id for suspect in case.suspects}
    if answer.culprit_id not in suspect_ids:
        raise CaseDataError(f"범인 {answer.culprit_id}가 용의자 목록에 없습니다.")
    # 정답이 가리키는 증거가 사건 증거에 있어야 함
    evidence_ids = {item.id for item in case.evidence}
    for evidence_id in [*answer.decisive_evidence_ids, *answer.misleading_evidence_ids]:
        if evidence_id not in evidence_ids:
            raise CaseDataError(f"증거 {evidence_id}가 사건 증거에 없습니다.")
    # 결정적 증거와 오해 유발 증거가 겹치면 안 됨
    overlap = set(answer.decisive_evidence_ids) & set(answer.misleading_evidence_ids)
    if overlap:
        raise CaseDataError(
            f"결정적 증거와 오해 유발 증거가 겹칩니다: {sorted(overlap)}"
        )
