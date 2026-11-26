import { useEffect, useState } from "react";

import { ApiError, fetchCase, fetchInvestigationResult } from "../services/api";
import type { InvestigationResult, PublicCase } from "../types/api";
import {
  useInvestigationEvents,
  type InvestigationEventsState,
} from "./useInvestigationEvents";

// 수사 실행 훅 결과
// 수사 결과·공개 사건 정보·기록 없음·불러오기 오류와 이벤트 스트림 상태를 담는 타입
export interface InvestigationRunState extends InvestigationEventsState {
  // 수사 결과 (불러오기 전이면 null)
  result: InvestigationResult | null;
  // 공개 사건 정보 (불러오기 전이면 null)
  publicCase: PublicCase | null;
  // 수사 기록이 없는지 (404)
  notFound: boolean;
  // 불러오기 오류 문장
  loadError: string | null;
}

// 수사 실행 훅
// 수사 결과와 사건 정보를 불러오고, 이벤트 스트림으로 종료를 기다렸다가 결과를 다시 조회하는 커스텀 훅
export function useInvestigationRun(
  investigationId: string,
): InvestigationRunState {
  // 수사 결과, 공개 사건 정보, 기록 없음, 불러오기 오류
  const [result, setResult] = useState<InvestigationResult | null>(null);
  const [publicCase, setPublicCase] = useState<PublicCase | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  // 처음에 결과 → 사건 정보 순서로 불러오기
  useEffect(() => {
    // 언마운트 후 상태 변경 방지 플래그
    let active = true;
    fetchInvestigationResult(investigationId)
      .then(async (data) => {
        if (!active) return;
        // 결과 저장 후 공개 사건 정보 조회
        setResult(data);
        const caseInfo = await fetchCase(data.case_id);
        if (active) setPublicCase(caseInfo);
      })
      .catch((caught: unknown) => {
        if (!active) return;
        // 404면 기록 없음 안내, 그 외는 오류 문장
        if (caught instanceof ApiError && caught.status === 404) {
          setNotFound(true);
        } else {
          setLoadError(
            caught instanceof Error
              ? caught.message
              : "수사를 불러오지 못했어요.",
          );
        }
      });
    // 정리 함수
    return () => {
      active = false;
    };
  }, [investigationId]);

  // 결과를 받은 뒤 이벤트 스트림 연결 (처음부터)
  const eventsState = useInvestigationEvents(result ? investigationId : null);
  const { done } = eventsState;

  // 마지막 이벤트를 받으면 결과를 다시 조회 (보고서·채점 포함)
  useEffect(() => {
    // 끝나지 않았으면 무시
    if (!done) return;
    let active = true;
    fetchInvestigationResult(investigationId)
      .then((data) => {
        if (active) setResult(data);
      })
      .catch((caught: unknown) => {
        if (active) {
          setLoadError(
            caught instanceof Error
              ? caught.message
              : "결과를 불러오지 못했어요.",
          );
        }
      });
    // 정리 함수
    return () => {
      active = false;
    };
  }, [done, investigationId]);

  // 상태 묶어 반환
  return { ...eventsState, result, publicCase, notFound, loadError };
}
