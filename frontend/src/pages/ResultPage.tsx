import { useEffect } from "react";
import { Link, Navigate, useParams } from "react-router";

import { PageContainer } from "../components/PageContainer";
import { ResultReveal } from "../components/ResultReveal";
import { useInvestigationRun } from "../hooks/useInvestigationRun";
import { useStoredProgress } from "../hooks/useStoredProgress";

// 결과 화면
// 주소의 수사 ID로 결과 보기를 그리며, 수사가 바뀌면 상태를 새로 시작하는 컴포넌트
export function ResultPage() {
  // 주소의 수사 ID
  const { investigationId = "" } = useParams();
  // 수사 ID마다 새로 그리기
  return <ResultView key={investigationId} investigationId={investigationId} />;
}

// 결과 보기 속성
interface ResultViewProps {
  // 수사 ID
  investigationId: string;
}

// 결과 보기
// 범인을 고른 뒤 AI 수사가 끝나면 결과를 보여 주고, 끝나기 전이면 종료를 기다렸다가 자동으로 보여 주는 컴포넌트
function ResultView({ investigationId }: ResultViewProps) {
  // 수사 결과·사건 정보·이벤트 스트림 상태
  const {
    result,
    publicCase,
    notFound,
    loadError,
    connection,
    done,
    reconnect,
  } = useInvestigationRun(investigationId);
  // 저장된 진행 상태 (고른 값)
  const [progress] = useStoredProgress(investigationId);

  // 처음 들어오면 페이지 맨 위에서 시작
  useEffect(() => {
    window.scrollTo(0, 0);
  }, []);

  // 아직 고르지 않았으면 수사 화면으로 이동 (정답이 먼저 보이지 않게)
  if (progress.pickedSuspect === null) {
    return <Navigate to={`/investigations/${investigationId}`} replace />;
  }

  // 기록 없음 안내
  if (notFound) {
    return (
      <PageContainer>
        <p className="text-slate-300">
          수사 기록이 없어요(서버 재시작 또는 1시간 경과).
        </p>
        <Link to="/" className="mt-4 inline-block text-sky-400 underline">
          사건 목록으로
        </Link>
      </PageContainer>
    );
  }

  // 불러오는 중
  if (!result) {
    return (
      <PageContainer>
        {loadError ? (
          <p className="text-sm text-red-400">{loadError}</p>
        ) : (
          <p className="text-sm text-slate-300">수사 정보를 불러오는 중...</p>
        )}
      </PageContainer>
    );
  }

  // 결과 공개 조건: 스트림이 끝났고 종료 상태의 결과를 다시 받았을 때
  const finished =
    done &&
    (result.status === "completed" ||
      result.status === "inconclusive" ||
      result.status === "failed") &&
    result.grading !== null;

  return (
    <PageContainer>
      {/* 목록으로 가기와 사건 제목 */}
      <Link to="/" className="text-sm text-sky-400 underline">
        ← 사건 목록
      </Link>
      <h1 className="mt-3 text-2xl font-bold">
        {publicCase?.title ?? result.case_id}
      </h1>

      <div className="mt-6 space-y-6">
        {finished ? (
          // 결과 (오류면 판정 카드와 내 선택·실제 범인만)
          <ResultReveal
            pick={progress.pickedSuspect}
            pickedAtStep={progress.pickedAtStep ?? 0}
            result={result}
            publicCase={publicCase}
          />
        ) : (
          // 대기 안내와 연결 상태
          <div className="space-y-3">
            <p className="text-sm text-amber-300">
              AI 수사관의 수사가 끝나면 정답을 공개해요
            </p>
            {!done && connection === "reconnecting" && (
              <p className="text-sm text-amber-300">
                연결이 끊겨 다시 연결하는 중이에요...
              </p>
            )}
            {!done && connection === "failed" && (
              <div>
                <p className="text-sm text-red-400">
                  서버와 연결하지 못했어요.
                </p>
                <button
                  type="button"
                  onClick={reconnect}
                  className="mt-2 min-h-11 rounded-lg bg-slate-700 px-4 text-sm font-medium hover:bg-slate-600"
                >
                  다시 연결
                </button>
              </div>
            )}
          </div>
        )}

        {/* 단서 다시 보기 / 새 수사 */}
        <div className="flex flex-col gap-2 sm:flex-row">
          <Link
            to={`/investigations/${investigationId}?review=1`}
            className="flex min-h-12 flex-1 items-center justify-center rounded-lg bg-sky-600 px-4 font-semibold hover:bg-sky-500"
          >
            단서 다시 보기
          </Link>
          <Link
            to="/"
            className="flex min-h-12 flex-1 items-center justify-center rounded-lg bg-slate-700 px-4 font-semibold hover:bg-slate-600"
          >
            새 수사
          </Link>
        </div>
      </div>
    </PageContainer>
  );
}
