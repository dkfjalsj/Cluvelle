from typing import Literal

from pydantic import BaseModel, Field, model_validator


# 최종 보고서
# 수사 결과(지목 또는 판단 보류)와 근거 증거·불일치·미확인 사항·설명을 담는 클래스
class FinalReport(BaseModel):
    # 결론 종류 (accuse: 지목, withhold: 판단 보류)
    verdict: Literal["accuse", "withhold"] = Field(
        description="accuse(용의자 지목) 또는 withhold(판단 보류)"
    )
    # 지목한 용의자 ID (accuse면 필수, withhold면 null)
    suspect_id: str | None = Field(description="지목한 용의자 ID. withhold면 null")
    # 근거로 인용한 확보 증거 ID 목록
    cited_evidence_ids: list[str] = Field(
        description="근거로 인용한 확보 증거 ID 목록. accuse면 1개 이상"
    )
    # 발견한 진술·기록 불일치 요약
    contradictions: list[str] = Field(description="발견한 진술·기록 불일치 요약")
    # 확인하지 못한 사항
    unverified: list[str] = Field(description="확인하지 못한 사항")
    # 증거를 인용한 추론
    explanation: str = Field(description="증거 ID를 인용한 추론 설명")

    # 결론과 용의자 일치 검증
    # accuse면 용의자가 있고 withhold면 용의자가 없는지 확인하는 함수
    @model_validator(mode="after")
    def validate_verdict_suspect(self) -> "FinalReport":
        # 지목인데 용의자가 없으면 오류
        if self.verdict == "accuse" and not self.suspect_id:
            raise ValueError("verdict가 accuse면 suspect_id가 있어야 합니다.")
        # 판단 보류인데 용의자가 있으면 오류
        if self.verdict == "withhold" and self.suspect_id is not None:
            raise ValueError("verdict가 withhold면 suspect_id는 null이어야 합니다.")
        # 검증된 객체 반환
        return self
