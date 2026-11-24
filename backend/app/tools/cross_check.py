from app.schemas.case import OFF_SITE_PLACE, CaseFile, Evidence, Fact
from app.schemas.tool import CrossCheckResult, FactRelation, RelationType
from app.tools.errors import ToolArgumentError

# 교차 검증 입력 증거 개수 범위
MIN_EVIDENCE_COUNT = 2
MAX_EVIDENCE_COUNT = 5

# 사실 종류 표기
KIND_LABELS = {"claim": "진술", "record": "기록"}
# 신원 미상 인물 표기
UNIDENTIFIED_LABEL = "신원 미상"

# 관계 종류별 끝부분 문구 (사실만 표현)
RELATION_PHRASES: dict[RelationType, str] = {
    "same_person_overlap_different_place": "같은 인물, 시간대 겹침, 장소 다름",
    "same_person_overlap_same_place": "같은 인물, 시간대 겹침, 장소 같음",
    "different_people_same_place_overlap": "서로 다른 인물, 시간대 겹침, 장소 같음",
    "unidentified_time_overlap": "신원 미상 기록 포함, 시간대 겹침",
}

# 관계가 없을 때 안내 문구
NO_RELATION_MESSAGE = "비교 가능한 시간·장소 관계가 없습니다."


# 증거 교차 검증
# 서로 다른 증거의 사실 관계(인물·장소·시간)를 규칙으로 비교해 관계 목록을 반환하는 함수
# 증거를 이미 확보했는지는 여기서 검사하지 않는다 (에이전트 단계에서 검사)
def cross_check_evidence(case: CaseFile, evidence_ids: list[str]) -> CrossCheckResult:
    # 입력 검증 후 증거 객체 목록 (입력 순서 유지)
    items = _resolve_evidence(case, evidence_ids)
    # 인물·장소 이름 조회 표
    suspect_names = {suspect.id: suspect.name for suspect in case.suspects}
    location_names = {location.id: location.name for location in case.locations}

    # 계산된 관계 목록과 중복 방지용 키 집합
    relations: list[FactRelation] = []
    seen: set[tuple[str, tuple[str, ...], tuple[str, ...], str]] = set()

    # 입력 순서대로 서로 다른 증거 쌍만 비교
    for index, first in enumerate(items):
        for second in items[index + 1 :]:
            # 두 증거의 사실 쌍마다 규칙 적용
            for fact_a in first.facts:
                for fact_b in second.facts:
                    # 규칙으로 관계 종류 결정 (없으면 건너뜀)
                    relation_type = _classify(fact_a, fact_b)
                    if relation_type is None:
                        continue
                    # 사실만 담은 설명 문장 생성
                    first_text = _describe(
                        first.id,
                        fact_a,
                        suspect_names,
                        location_names,
                        case.off_site_label,
                    )
                    second_text = _describe(
                        second.id,
                        fact_b,
                        suspect_names,
                        location_names,
                        case.off_site_label,
                    )
                    detail = f"{first_text} / {second_text} → {RELATION_PHRASES[relation_type]}"
                    # 관계 객체 생성
                    relation = FactRelation(
                        type=relation_type,
                        evidence_ids=[first.id, second.id],
                        person_ids=_person_ids(fact_a, fact_b),
                        detail=detail,
                    )
                    # 같은 관계는 한 번만 추가
                    key = (
                        relation.type,
                        tuple(relation.evidence_ids),
                        tuple(relation.person_ids),
                        relation.detail,
                    )
                    if key in seen:
                        continue
                    seen.add(key)
                    relations.append(relation)

    # 관계 수에 맞는 안내 문구 선택
    message = f"사실 관계 {len(relations)}건" if relations else NO_RELATION_MESSAGE
    # 결과 반환
    return CrossCheckResult(
        tool="cross_check_evidence",
        evidence_ids=list(evidence_ids),
        relations=relations,
        message=message,
    )


# 입력 증거 확인
# 증거 ID 개수·중복·존재 여부를 검사하고 입력 순서대로 증거 객체를 반환하는 함수
def _resolve_evidence(case: CaseFile, evidence_ids: list[str]) -> list[Evidence]:
    # 개수가 범위를 벗어나면 오류
    if not MIN_EVIDENCE_COUNT <= len(evidence_ids) <= MAX_EVIDENCE_COUNT:
        raise ToolArgumentError(
            f"교차 검증할 증거는 {MIN_EVIDENCE_COUNT}~{MAX_EVIDENCE_COUNT}개여야 합니다: "
            f"{len(evidence_ids)}개"
        )
    # 증거 ID 조회 표
    evidence_by_id = {item.id: item for item in case.evidence}
    # 이미 본 ID 집합
    seen: set[str] = set()
    # ID마다 중복·존재 여부 확인
    for evidence_id in evidence_ids:
        # 중복이면 오류
        if evidence_id in seen:
            raise ToolArgumentError(f"중복된 증거 ID가 있습니다: {evidence_id}")
        # 사건에 없는 증거면 오류
        if evidence_id not in evidence_by_id:
            raise ToolArgumentError(f"사건에 없는 증거입니다: {evidence_id}")
        # 본 ID로 기록
        seen.add(evidence_id)
    # 입력 순서대로 증거 객체 반환
    return [evidence_by_id[evidence_id] for evidence_id in evidence_ids]


# 관계 종류 판정
# 두 사실의 인물·시간·장소를 규칙 순서대로 비교해 관계 종류를 반환하는 함수 (없으면 None)
def _classify(fact_a: Fact, fact_b: Fact) -> RelationType | None:
    # 시간 겹침 여부
    overlap = _overlaps(fact_a, fact_b)
    # 규칙 1: 두 인물이 모두 있고 같음
    if (
        fact_a.person_id is not None
        and fact_b.person_id is not None
        and fact_a.person_id == fact_b.person_id
    ):
        # 겹치지 않으면 관계 없음
        if not overlap:
            return None
        # 겹치면 장소 같음/다름으로 구분
        if fact_a.place == fact_b.place:
            return "same_person_overlap_same_place"
        return "same_person_overlap_different_place"
    # 규칙 2: 두 인물이 모두 있고 다름 (겹치고 장소가 같을 때만 관계)
    if fact_a.person_id is not None and fact_b.person_id is not None:
        if overlap and fact_a.place == fact_b.place:
            return "different_people_same_place_overlap"
        return None
    # 규칙 3: 하나라도 신원 미상 (겹칠 때만 관계)
    if overlap:
        return "unidentified_time_overlap"
    return None


# 시간 겹침 판정
# 두 사실의 시간 구간이 겹치는지 반환하는 함수 (길이 있는 두 구간이 끝점에서만 맞닿으면 겹침 아님)
def _overlaps(fact_a: Fact, fact_b: Fact) -> bool:
    # HH:MM을 분으로 변환
    a_start, a_end = _to_minutes(fact_a.start), _to_minutes(fact_a.end)
    b_start, b_end = _to_minutes(fact_b.start), _to_minutes(fact_b.end)
    # 경계 포함 기준으로 겹치지 않으면 False
    if not (a_start <= b_end and b_start <= a_end):
        return False
    # 공통 구간이 한 시점뿐인지 확인
    touches_only = max(a_start, b_start) == min(a_end, b_end)
    # 한 시점만 공유할 때는 둘 중 하나가 순간 기록이어야 겹침으로 봄
    if touches_only:
        return a_start == a_end or b_start == b_end
    # 공통 구간이 길이를 가지면 겹침
    return True


# 분 변환
# HH:MM 문자열을 자정 기준 분으로 바꾸는 함수
def _to_minutes(value: str) -> int:
    # 시와 분으로 나눠 분 단위로 합산
    hours, minutes = value.split(":")
    return int(hours) * 60 + int(minutes)


# 사실 설명
# 증거 ID·종류·인물·장소·시간을 정해진 형식의 문자열로 만드는 함수
def _describe(
    evidence_id: str,
    fact: Fact,
    suspect_names: dict[str, str],
    location_names: dict[str, str],
    off_site_label: str,
) -> str:
    # 종류 표기 (진술/기록)
    kind = KIND_LABELS[fact.kind]
    # 인물 표기 (신원 미상이면 고정 문구)
    if fact.person_id is None:
        person = UNIDENTIFIED_LABEL
    else:
        person = f"{fact.person_id}({suspect_names[fact.person_id]})"
    # 장소 표기 (사건 밖이면 사건 파일에 정한 표기)
    if fact.place == OFF_SITE_PLACE:
        place = off_site_label
    else:
        place = f"{fact.place}({location_names[fact.place]})"
    # 형식에 맞춰 조합
    return f"{evidence_id}({kind}) {person} {place} {fact.start}-{fact.end}"


# 확인된 인물 ID 목록
# 두 사실에서 신원이 확인된 인물 ID를 등장 순서대로 중복 없이 반환하는 함수
def _person_ids(fact_a: Fact, fact_b: Fact) -> list[str]:
    # 인물 ID 목록
    person_ids: list[str] = []
    # 신원 미상은 빼고 처음 나온 인물만 추가
    for person_id in (fact_a.person_id, fact_b.person_id):
        if person_id is not None and person_id not in person_ids:
            person_ids.append(person_id)
    # 목록 반환
    return person_ids
