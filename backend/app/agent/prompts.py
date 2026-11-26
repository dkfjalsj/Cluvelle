from app.schemas.case import PublicCase

# 프롬프트 버전
PROMPT_VERSION = "adaptive-v4"

# 시스템 프롬프트
SYSTEM_PROMPT = """너는 가상 미스터리 사건을 수사하는 AI 탐정이다.
규칙:
1. 정보는 제공된 조사 도구로만 얻는다. 도구로 확인하지 않은 사실을 지어내지 않는다.
2. 조사 예산은 사건마다 정해져 있고, 모든 도구 호출(교차 검증, 잘못된 호출 포함)이 1회씩 차감된다.
3. 도구를 부를 때마다 reason에 지금 그 도구를 고른 이유를 한 문장으로 적는다.
4. 조사 결과를 보고 가설을 고치고 다음 조사를 정한다. 같은 조사를 반복하지 않는다.
5. 교차 검증에는 이미 확보한 증거 ID만 넣는다.
6. 충분히 조사했거나 더 조사할 가치가 없으면 도구를 부르지 말고 "수사를 마칩니다."라고만 답한다. 최종 보고서는 이후 따로 요청된다.
7. 도구 결과 끝의 남은 조사 예산을 보고 계획을 조정한다.
8. 도구를 부를 때마다 hypothesis에 현재 가설을 한 문장으로 적는다. 아직 가설이 없으면 그렇게 적는다. hypothesis에는 특정 용의자가 범인이라고 단정하는 표현을 쓰지 않는다. 지금 어떤 가능성을 보고 있고 무엇을 확인해야 하는지를 적는다. 용의자 이름은 확인 대상으로만 언급할 수 있다."""


# 이름과 설명 표기
# 설명이 있으면 "이름 - 설명", 없으면 이름만 반환하는 함수
def _with_description(name: str, description: str | None) -> str:
    # 설명이 없으면 이름만
    if description is None:
        return name
    # 설명이 있으면 이름 뒤에 붙임
    return f"{name} - {description}"


# 고정 계획형 프롬프트 버전
FIXED_PROMPT_VERSION = "fixed-v1"

# 고정 계획형 계획 수립 시스템 프롬프트
PLANNER_SYSTEM_PROMPT = """너는 가상 미스터리 사건을 수사하는 AI 탐정이다. 이번에는 조사를 시작하기 전에 전체 조사 계획을 한 번에 세운다.
규칙:
1. 정보는 제공된 조사 도구로만 얻는다. 계획을 세운 뒤에는 결과를 보고 계획을 바꿀 수 없다.
2. 계획의 단계 수는 조사 예산 이하로 한다. 모든 단계(교차 검증, 잘못된 단계 포함)가 예산을 1회씩 차감한다.
3. 각 단계에는 도구 이름과 그 도구에 필요한 인자, 그리고 reason(그 단계를 계획한 이유 한 문장)을 적는다.
4. 같은 조사를 반복하지 않는다.
5. 교차 검증(cross_check_evidence)은 source_steps에 앞선 단계 번호를 적으면, 그 단계들에서 나온 증거 전체로 비교한다. 증거가 2~5개가 아니면 실패한다.
6. 공개된 장소·용의자·주제·카메라·시간대만 사용한다."""


# 계획 요청 문구 생성
# 사건 브리핑 뒤에 붙일 조사 계획 요청 문구를 반환하는 함수
def build_plan_request() -> str:
    # 고정 요청 문구 반환
    return "위 사건에 대한 조사 계획을 세워라."


# 보고서 요청 문구 생성
# 확보 증거와 용의자 목록을 넣어 최종 보고서 작성을 요청하는 문구를 만드는 함수
def build_report_request(collected_ids: list[str], suspect_ids: list[str]) -> str:
    # 확보 증거 목록 (없으면 "없음")
    collected_text = ", ".join(collected_ids) if collected_ids else "없음"
    # 용의자 목록
    suspect_text = ", ".join(suspect_ids)
    # 요청 문구 조합
    return "\n".join(
        [
            "수사를 종료하고 최종 보고서를 작성하라.",
            f"- 인용할 수 있는 증거는 지금까지 확보한 증거뿐이다: {collected_text}",
            f"- 지목할 수 있는 용의자: {suspect_text}",
            "- 확보한 증거만으로 한 사람을 뒷받침할 수 없으면 verdict를 withhold(판단 보류)로 한다.",
            "- accuse면 suspect_id와 근거 증거 ID를 1개 이상 적는다.",
            "- 확인하지 못한 점은 unverified에 적는다.",
        ]
    )


# 보고서 재작성 요청 문구 생성
# 검증에 실패한 이유 목록을 넣어 보고서를 다시 쓰라고 요청하는 문구를 만드는 함수
def build_report_feedback(errors: list[str]) -> str:
    # 오류마다 한 줄씩
    lines = [f"- {error}" for error in errors]
    # 안내 문구와 합쳐 반환
    return "보고서가 검증에 실패했다. 아래 문제를 고쳐 다시 작성하라:\n" + "\n".join(
        lines
    )


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
        lines.append(
            f"- {location.id} {_with_description(location.name, location.description)}"
        )
    # 카메라 목록 (ID·이름·조회 가능 시간대)
    lines.append("")
    lines.append("카메라:")
    for camera in public_case.cameras:
        windows = ", ".join(camera.time_windows)
        label = _with_description(camera.name, camera.description)
        lines.append(f"- {camera.id} {label} (조회 가능 시간대: {windows})")
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
