import { useCallback, useEffect, useState } from "react";

import { CaseCard } from "../components/CaseCard";
import { PageContainer } from "../components/PageContainer";
import { CaseListSkeleton } from "../components/Skeletons";
import { useDelayedFlag } from "../hooks/useDelayedFlag";
import { fetchCases } from "../services/api";
import type { CaseListItem } from "../types/api";

// 서버 깨우기 안내를 보여 줄 로딩 시간(ms)
const WAKE_NOTICE_DELAY_MS = 3000;

// 사건 목록 화면
// 사건 카드 목록을 보여 주고, 로딩이 길면 서버 깨우기 안내를, 실패하면 다시 시도 버튼을 보여 주는 컴포넌트
export function CaseListPage() {
  // 사건 목록, 로딩 여부, 오류 문장
  const [cases, setCases] = useState<CaseListItem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // 로딩이 3초를 넘었는지
  const showWakeNotice = useDelayedFlag(loading, WAKE_NOTICE_DELAY_MS);

  // 목록 불러오기
  // 사건 목록을 요청해 상태에 반영하는 함수
  const load = useCallback(async () => {
    // 로딩 시작
    setLoading(true);
    setError(null);
    try {
      // 목록 저장
      setCases(await fetchCases());
    } catch (caught) {
      // 오류 문장 저장
      setError(
        caught instanceof Error ? caught.message : "목록을 불러오지 못했어요.",
      );
    } finally {
      // 로딩 끝
      setLoading(false);
    }
  }, []);

  // 처음 한 번 불러오기 (상태 변경은 응답 콜백에서만)
  useEffect(() => {
    // 언마운트 후 상태 변경 방지 플래그
    let active = true;
    fetchCases()
      .then((data) => {
        // 목록 저장
        if (active) setCases(data);
      })
      .catch((caught: unknown) => {
        // 오류 문장 저장
        if (active) {
          setError(
            caught instanceof Error
              ? caught.message
              : "목록을 불러오지 못했어요.",
          );
        }
      })
      .finally(() => {
        // 로딩 끝
        if (active) setLoading(false);
      });
    // 정리 함수
    return () => {
      active = false;
    };
  }, []);

  return (
    <PageContainer>
      {/* 안내 문장 (앱 이름은 머리글에 표시) */}
      <p className="text-sm text-slate-400">
        사건을 고르면 AI 수사관이 조사를 시작해요.
      </p>

      {/* 로딩 중 안내와 스켈레톤 */}
      {loading && (
        <div className="mt-6 text-sm text-slate-300">
          <p>사건 목록을 불러오는 중...</p>
          {showWakeNotice && (
            <p className="mt-2 text-amber-300">
              서버를 깨우는 중이에요. 최대 1분쯤 걸릴 수 있어요.
            </p>
          )}
          <div className="mt-4">
            <CaseListSkeleton />
          </div>
        </div>
      )}

      {/* 실패 시 오류 문장과 다시 시도 */}
      {!loading && error && (
        <div className="mt-6">
          <p className="text-sm text-red-400">{error}</p>
          <button
            type="button"
            onClick={() => void load()}
            className="mt-3 min-h-11 rounded-lg bg-slate-700 px-4 text-sm font-medium hover:bg-slate-600"
          >
            다시 시도
          </button>
        </div>
      )}

      {/* 사건 카드 목록 */}
      {!loading && !error && cases && (
        <ul className="mt-6 grid gap-3 lg:grid-cols-2">
          {cases.map((item) => (
            <li key={item.case_id}>
              <CaseCard item={item} />
            </li>
          ))}
        </ul>
      )}
    </PageContainer>
  );
}
