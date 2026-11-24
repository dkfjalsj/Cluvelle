import re
from pathlib import Path

from pydantic import ValidationError

from app.schemas.case import CASE_ID_PATTERN, CaseFile, CaseSummary, PublicCase

# 기본 사건 폴더 경로 (backend/data/cases)
DEFAULT_CASES_DIR = Path(__file__).resolve().parents[2] / "data" / "cases"


# 사건 ID 형식 오류
# 사건 ID가 CASE-### 형식이 아닐 때 발생시키는 예외 클래스
class InvalidCaseIdError(ValueError):
    pass


# 사건 없음 오류
# 사건 ID에 해당하는 파일이 없을 때 발생시키는 예외 클래스
class CaseNotFoundError(LookupError):
    pass


# 사건 데이터 오류
# 사건 파일 내용이 스키마·정합성 검증에 실패했을 때 원인과 함께 발생시키는 예외 클래스
class CaseDataError(ValueError):
    pass


# 사건 ID 형식 검사
# 사건 ID가 CASE-### 형식인지 확인하고 아니면 오류를 내는 함수
def ensure_valid_case_id(case_id: str) -> None:
    # 형식이 맞지 않으면 오류 (경로 조작 문자열도 여기서 차단)
    if re.fullmatch(CASE_ID_PATTERN, case_id) is None:
        raise InvalidCaseIdError(f"사건 ID 형식이 올바르지 않습니다: {case_id!r}")


# 사건 저장소
# 사건 폴더의 JSON 파일을 읽어 검증하고 공개 정보·요약으로 변환하는 클래스
class CaseRepository:
    # 저장소 생성
    # 사건 폴더 경로를 받아 저장소를 초기화하는 함수
    def __init__(self, cases_dir: Path = DEFAULT_CASES_DIR) -> None:
        # 사건 파일을 읽을 폴더
        self.cases_dir = cases_dir

    # 사건 ID 목록 조회
    # 폴더의 CASE-###.json 파일 이름에서 사건 ID를 정렬해 반환하는 함수
    def list_case_ids(self) -> list[str]:
        # 폴더의 JSON 파일 중 이름이 사건 ID 형식인 것만 선택
        case_ids = [
            path.stem
            for path in self.cases_dir.glob("*.json")
            if re.fullmatch(CASE_ID_PATTERN, path.stem) is not None
        ]
        # 정렬해 반환
        return sorted(case_ids)

    # 사건 파일 로드
    # 사건 ID로 파일을 읽어 스키마 검증을 거친 사건 데이터를 반환하는 함수
    def load_case(self, case_id: str) -> CaseFile:
        # ID 형식 검사
        ensure_valid_case_id(case_id)
        # 사건 파일 경로
        path = self.cases_dir / f"{case_id}.json"
        # 파일이 없으면 오류
        if not path.is_file():
            raise CaseNotFoundError(f"사건을 찾을 수 없습니다: {case_id}")
        # 파일 읽기 후 스키마 검증
        try:
            case = CaseFile.model_validate_json(path.read_text(encoding="utf-8"))
        except ValidationError as error:
            # 검증 실패 원인을 담아 오류 변환
            raise CaseDataError(
                f"사건 {case_id} 데이터가 올바르지 않습니다: {error}"
            ) from error
        # 파일 이름의 ID와 내용의 ID가 다르면 오류
        if case.case_id != case_id:
            raise CaseDataError(
                f"파일 이름의 사건 ID({case_id})와 내용의 case_id({case.case_id})가 다릅니다."
            )
        # 검증된 사건 반환
        return case

    # 공개 사건 정보 조회
    # 사건 파일에서 증거를 뺀 공개 정보만 반환하는 함수
    def get_public_case(self, case_id: str) -> PublicCase:
        # 사건 파일 로드
        case = self.load_case(case_id)
        # 증거를 제외하고 공개 모델로 변환
        return PublicCase.model_validate(case.model_dump(exclude={"evidence"}))

    # 사건 요약 목록 조회
    # 모든 사건의 ID·제목·난이도·한 줄 소개를 ID 순서로 반환하는 함수
    def list_summaries(self) -> list[CaseSummary]:
        # 요약 목록
        summaries: list[CaseSummary] = []
        # 사건마다 로드해 요약 생성
        for case_id in self.list_case_ids():
            case = self.load_case(case_id)
            summaries.append(
                CaseSummary(
                    case_id=case.case_id,
                    title=case.title,
                    difficulty=case.difficulty,
                    summary=case.summary,
                )
            )
        # 요약 목록 반환
        return summaries
