from itertools import combinations

import pytest

from app.schemas.case import CaseFile
from app.schemas.tool import CrossCheckResult, FactRelation
from app.services.case_repository import CaseRepository
from app.tools import ToolArgumentError, cross_check_evidence

# 설명·안내 문구에 나오면 안 되는 단어
FORBIDDEN_WORDS = (
    "거짓",
    "범인",
    "모순",
    "의심",
    "유죄",
    "진실",
    "확정",
    "거짓말",
    "범행",
)
# [E9, E19] 교차 검증의 기대 설명 문장
EXPECTED_E9_E19_DETAIL = (
    "E9(진술) S3(정민혁) 연구동 밖 20:40-23:00 / "
    "E19(기록) S3(정민혁) L5(주차장) 22:03-22:05 → 같은 인물, 시간대 겹침, 장소 다름"
)


# CASE-001 픽스처
# 기본 경로에서 CASE-001을 로드해 반환하는 함수
@pytest.fixture
def case() -> CaseFile:
    # 기본 사건 폴더에서 로드
    return CaseRepository().load_case("CASE-001")


# 관계 종류별 필터
# 교차 검증 결과에서 지정한 종류의 관계만 골라 반환하는 함수
def relations_of(result: CrossCheckResult, relation_type: str) -> list[FactRelation]:
    # 종류가 같은 관계만 반환
    return [item for item in result.relations if item.type == relation_type]


# E9·E19 테스트
# S3의 연구동 밖 진술과 주차장 기록이 같은 인물·시간 겹침·장소 다름으로 나오는지 확인하는 함수
def test_e9_e19_same_person_different_place(case: CaseFile) -> None:
    # 교차 검증 실행
    result = cross_check_evidence(case, ["E9", "E19"])
    # 해당 관계가 정확히 1건
    matched = relations_of(result, "same_person_overlap_different_place")
    assert len(matched) == 1
    # 인물·증거·설명 확인
    assert matched[0].person_ids == ["S3"]
    assert matched[0].evidence_ids == ["E9", "E19"]
    assert matched[0].detail == EXPECTED_E9_E19_DETAIL


# E9·E18 테스트
# 신원 미상 차량 기록과는 같은 인물 관계 없이 신원 미상 시간 겹침 1건만 나오는지 확인하는 함수
def test_e9_e18_unidentified_overlap(case: CaseFile) -> None:
    # 교차 검증 실행
    result = cross_check_evidence(case, ["E9", "E18"])
    # 같은 인물 관계는 없어야 함
    assert not [
        item for item in result.relations if item.type.startswith("same_person")
    ]
    # 신원 미상 시간 겹침이 정확히 1건
    matched = relations_of(result, "unidentified_time_overlap")
    assert len(matched) == 1
    # E9의 연구동 밖 20:40-23:00 사실과 E18의 21:35 기록 사이 관계
    assert "연구동 밖 20:40-23:00" in matched[0].detail
    assert "E18(기록) 신원 미상 L5(주차장) 21:35-21:35" in matched[0].detail
    # 확인된 인물만 담김
    assert matched[0].person_ids == ["S3"]


# E3·E16 테스트
# S1의 실험실 진술과 복도 기록이 같은 인물·시간 겹침·장소 다름 1건으로 나오는지 확인하는 함수
def test_e3_e16_same_person_different_place(case: CaseFile) -> None:
    # 교차 검증 실행
    result = cross_check_evidence(case, ["E3", "E16"])
    # 해당 관계가 정확히 1건
    matched = relations_of(result, "same_person_overlap_different_place")
    assert len(matched) == 1
    # L1 21:05-21:09 진술과 L2 21:05-21:10 기록 사이 관계
    assert matched[0].person_ids == ["S1"]
    assert "L1(실험실 (보관함 있음)) 21:05-21:09" in matched[0].detail
    assert "L2(3층 복도) 21:05-21:10" in matched[0].detail


# E14·E21 테스트
# S2의 로비 CCTV 기록과 방문 종료 기록이 같은 인물·시간 겹침·장소 같음 1건으로 나오는지 확인하는 함수
def test_e14_e21_same_person_same_place(case: CaseFile) -> None:
    # 교차 검증 실행
    result = cross_check_evidence(case, ["E14", "E21"])
    # 해당 관계가 정확히 1건
    matched = relations_of(result, "same_person_overlap_same_place")
    assert len(matched) == 1
    # L6 21:20 기록끼리의 관계
    assert matched[0].person_ids == ["S2"]
    assert matched[0].detail.count("L6(1층 로비) 21:20-21:20") == 2


# 사실 없는 증거 테스트
# 두 증거 모두 사실 관계가 없으면 빈 관계와 고정 안내 문구가 나오는지 확인하는 함수
def test_evidence_without_facts(case: CaseFile) -> None:
    # 교차 검증 실행
    result = cross_check_evidence(case, ["E1", "E2"])
    # 관계 없음과 안내 문구 확인
    assert result.relations == []
    assert result.message == "비교 가능한 시간·장소 관계가 없습니다."


# 입력 오류 테스트
# 개수 부족·초과, 중복, 없는 증거 ID를 ToolArgumentError로 거부하는지 확인하는 함수
@pytest.mark.parametrize(
    "evidence_ids",
    [
        ["E1"],
        ["E1", "E2", "E3", "E4", "E5", "E6"],
        ["E1", "E1"],
        ["E1", "E99"],
    ],
)
def test_invalid_inputs(case: CaseFile, evidence_ids: list[str]) -> None:
    # 인자 오류 발생 확인
    with pytest.raises(ToolArgumentError):
        cross_check_evidence(case, evidence_ids)


# 금지 단어 전수 테스트
# 사실 관계가 있는 모든 증거 2개 조합의 설명·안내 문구에 금지 단어가 없는지 확인하는 함수
def test_no_forbidden_words_in_any_pair(case: CaseFile) -> None:
    # 사실 관계가 있는 증거 ID 목록
    ids_with_facts = [item.id for item in case.evidence if item.facts]
    # 모든 2개 조합 검사
    for pair in combinations(ids_with_facts, 2):
        result = cross_check_evidence(case, list(pair))
        # 안내 문구와 모든 설명 문장 모으기
        texts = [result.message, *(item.detail for item in result.relations)]
        # 금지 단어가 하나도 없어야 함
        for text in texts:
            for word in FORBIDDEN_WORDS:
                assert word not in text, (pair, word, text)


# 결정성 테스트
# 같은 입력으로 두 번 호출한 결과가 완전히 같은지 확인하는 함수
def test_deterministic(case: CaseFile) -> None:
    # 같은 입력으로 두 번 실행
    first = cross_check_evidence(case, ["E3", "E14", "E16", "E20"])
    second = cross_check_evidence(case, ["E3", "E14", "E16", "E20"])
    # 직렬화 결과까지 동일해야 함
    assert first == second
    assert first.model_dump_json() == second.model_dump_json()
