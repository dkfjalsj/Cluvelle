from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.schemas.api import CaseListItem
from app.schemas.case import CaseFile, PublicCase
from app.services.case_repository import (
    CaseNotFoundError,
    CaseRepository,
    InvalidCaseIdError,
)

# 사건 라우터
router = APIRouter()


# 오류 응답 생성
# 상태 코드·오류 코드·한국어 문장으로 {"detail": {"code", "message"}} 형식의 예외를 만드는 함수
def http_error(status_code: int, code: str, message: str) -> HTTPException:
    # 정해진 형식의 HTTP 예외 반환
    return HTTPException(
        status_code=status_code, detail={"code": code, "message": message}
    )


# 사건 저장소 의존성
# 기본 경로의 사건 저장소를 반환하는 함수 (테스트에서 교체 가능)
def get_case_repository() -> CaseRepository:
    # 기본 사건 저장소 반환
    return CaseRepository()


# 사건 저장소 의존성 주입 형식
RepositoryDep = Annotated[CaseRepository, Depends(get_case_repository)]


# 사건 로드 (오류 응답 변환)
# 사건을 로드하고 형식 오류는 400, 없는 사건은 404 응답 예외로 바꾸는 함수
def load_case_or_raise(repository: CaseRepository, case_id: str) -> CaseFile:
    # 사건 로드
    try:
        return repository.load_case(case_id)
    except InvalidCaseIdError as error:
        # 형식 오류
        raise http_error(
            400, "invalid_case_id", "사건 ID 형식이 올바르지 않습니다."
        ) from error
    except CaseNotFoundError as error:
        # 없는 사건
        raise http_error(404, "case_not_found", "사건을 찾을 수 없습니다.") from error


# 사건 목록 조회
# 모든 사건의 ID·제목·난이도·소개·예산을 사건 ID 순서로 반환하는 함수
@router.get("/api/cases")
def list_cases(repository: RepositoryDep) -> list[CaseListItem]:
    # 사건 ID 순서대로 목록 항목 생성
    items: list[CaseListItem] = []
    for case_id in repository.list_case_ids():
        case = repository.load_case(case_id)
        items.append(
            CaseListItem(
                case_id=case.case_id,
                title=case.title,
                difficulty=case.difficulty,
                summary=case.summary,
                tool_budget=case.tool_budget,
            )
        )
    # 목록 반환
    return items


# 사건 상세 조회
# 사건의 공개 정보만 반환하는 함수 (형식 오류 400, 없는 사건 404)
@router.get("/api/cases/{case_id}")
def get_case(case_id: str, repository: RepositoryDep) -> PublicCase:
    # 존재·형식 확인
    load_case_or_raise(repository, case_id)
    # 공개 정보 반환
    return repository.get_public_case(case_id)
