from app.schemas.case import CaseFile, EvidenceSourceTool
from app.schemas.tool import EvidenceView, InvestigationResult
from app.tools.errors import ToolArgumentError

# 증거가 없을 때 안내 문구
NOTHING_FOUND_MESSAGE = "특이사항 없음"


# 현장 조사
# 공개된 장소를 조사해 그 장소에 있는 증거를 반환하는 함수
def inspect_scene(case: CaseFile, location_id: str) -> InvestigationResult:
    # 장소가 공개 목록에 있는지 확인
    if location_id not in {location.id for location in case.locations}:
        raise ToolArgumentError(f"공개된 장소 목록에 없는 장소입니다: {location_id}")
    # 장소 locator가 일치하는 증거 조회
    return _investigate(case, "inspect_scene", {"location_id": location_id})


# 용의자 심문
# 공개된 용의자에게 공개된 주제로 질문해 그 진술 증거를 반환하는 함수
def interview_suspect(
    case: CaseFile, suspect_id: str, topic_id: str
) -> InvestigationResult:
    # 용의자가 공개 목록에 있는지 확인
    _ensure_suspect(case, suspect_id)
    # 주제가 공개 목록에 있는지 확인
    if topic_id not in {topic.id for topic in case.topics}:
        raise ToolArgumentError(f"공개된 질문 주제 목록에 없는 주제입니다: {topic_id}")
    # 용의자·주제 locator가 일치하는 증거 조회
    return _investigate(
        case,
        "interview_suspect",
        {"suspect_id": suspect_id, "topic_id": topic_id},
    )


# CCTV 확인
# 공개된 카메라의 조회 가능한 시간대를 확인해 그 CCTV 증거를 반환하는 함수
def check_cctv(case: CaseFile, camera_id: str, time_window: str) -> InvestigationResult:
    # 카메라 조회
    camera = next((item for item in case.cameras if item.id == camera_id), None)
    # 카메라가 공개 목록에 없으면 오류
    if camera is None:
        raise ToolArgumentError(f"공개된 카메라 목록에 없는 카메라입니다: {camera_id}")
    # 시간대가 그 카메라의 조회 가능 시간대에 없으면 오류
    if time_window not in camera.time_windows:
        raise ToolArgumentError(
            f"카메라 {camera_id}에서 조회할 수 없는 시간대입니다: {time_window}"
        )
    # 카메라·시간대 locator가 일치하는 증거 조회
    return _investigate(
        case,
        "check_cctv",
        {"camera_id": camera_id, "time_window": time_window},
    )


# 알리바이 확인
# 공개된 용의자의 출입·이동 기록 증거를 반환하는 함수
def verify_alibi(case: CaseFile, suspect_id: str) -> InvestigationResult:
    # 용의자가 공개 목록에 있는지 확인
    _ensure_suspect(case, suspect_id)
    # 용의자 locator가 일치하는 증거 조회
    return _investigate(case, "verify_alibi", {"suspect_id": suspect_id})


# 용의자 확인
# 용의자 ID가 공개된 용의자 목록에 없으면 오류를 내는 함수
def _ensure_suspect(case: CaseFile, suspect_id: str) -> None:
    # 공개 목록에 없으면 오류
    if suspect_id not in {suspect.id for suspect in case.suspects}:
        raise ToolArgumentError(f"공개된 용의자 목록에 없는 용의자입니다: {suspect_id}")


# 증거 조회
# 도구와 locator가 정확히 일치하는 증거를 사건 데이터 순서대로 모아 결과로 만드는 함수
def _investigate(
    case: CaseFile, tool: EvidenceSourceTool, locator: dict[str, str]
) -> InvestigationResult:
    # source_tool과 locator(값이 있는 필드)가 정확히 일치하는 증거 수집
    matched = [
        EvidenceView(id=item.id, source_tool=item.source_tool, summary=item.summary)
        for item in case.evidence
        if item.source_tool == tool
        and item.locator.model_dump(exclude_none=True) == locator
    ]
    # 증거가 있으면 확보 결과 반환
    if matched:
        return InvestigationResult(
            tool=tool,
            args=locator,
            found=True,
            evidence=matched,
            message=f"증거 {len(matched)}건을 확보했습니다.",
        )
    # 증거가 없으면 특이사항 없음 결과 반환
    return InvestigationResult(
        tool=tool,
        args=locator,
        found=False,
        evidence=[],
        message=NOTHING_FOUND_MESSAGE,
    )
