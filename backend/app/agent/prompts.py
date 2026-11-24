from app.schemas.case import PublicCase

# 프롬프트 버전
PROMPT_VERSION = "adaptive-v1"

# 시스템 프롬프트
SYSTEM_PROMPT = """너는 가상 미스터리 사건을 수사하는 AI 탐정이다.
규칙:
1. 정보는 제공된 조사 도구로만 얻는다. 도구로 확인하지 않은 사실을 지어내지 않는다.
2. 조사 예산은 사건마다 정해져 있고, 모든 도구 호출(교차 검증, 잘못된 호출 포함)이 1회씩 차감된다.
3. 도구를 부를 때마다 reason에 지금 그 도구를 고른 이유를 한 문장으로 적는다.
4. 조사 결과를 보고 가설을 고치고 다음 조사를 정한다. 같은 조사를 반복하지 않는다.
5. 교차 검증에는 이미 확보한 증거 ID만 넣는다.
6. 충분히 조사했거나 더 조사할 가치가 없으면 도구를 부르지 말고 결론을 쓴다.
결론 형식:
- 지목 용의자: 용의자 ID 하나 또는 "판단 보류"
- 근거 증거: 확보한 증거 ID 목록
- 설명: 증거를 인용한 추론 3~5문장
- 미확인 사항: 확인하지 못한 점"""


# 사건 브리핑 생성
# 공개 사건 정보만으로 AI에게 줄 사건 브리핑 문자열을 만드는 함수
def build_case_brief(public_case: PublicCase) -> str:
    # 제목·소개·예산
    lines = [
        f"사건: {public_case.title}",
        f"소개: {public_case.introduction}",
        f"조사 예산: {public_case.tool_budget}회",
        "",
        "용의자:",
    ]
    # 용의자 목록 (ID·이름·역할·설명)
    for suspect in public_case.suspects:
        lines.append(
            f"- {suspect.id} {suspect.name} ({suspect.role}): {suspect.description}"
        )
    # 장소 목록 (ID·이름)
    lines.append("")
    lines.append("장소:")
    for location in public_case.locations:
        lines.append(f"- {location.id} {location.name}")
    # 카메라 목록 (ID·이름·조회 가능 시간대)
    lines.append("")
    lines.append("카메라:")
    for camera in public_case.cameras:
        windows = ", ".join(camera.time_windows)
        lines.append(f"- {camera.id} {camera.name} (조회 가능 시간대: {windows})")
    # 질문 주제 목록 (ID·이름)
    lines.append("")
    lines.append("질문 주제:")
    for topic in public_case.topics:
        lines.append(f"- {topic.id} {topic.name}")
    # 사건 밖 장소 표기 안내
    lines.append("")
    lines.append(f'사건 현장 밖 장소는 "{public_case.off_site_label}"로 표기된다.')
    # 줄바꿈으로 합쳐 반환
    return "\n".join(lines)
