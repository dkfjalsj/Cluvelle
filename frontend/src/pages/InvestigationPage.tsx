import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router";

import { CaseInfo } from "../components/CaseInfo";
import { EvidenceList } from "../components/EvidenceList";
import { GuidePanel } from "../components/GuidePanel";
import { HypothesisLog } from "../components/HypothesisLog";
import { PageContainer } from "../components/PageContainer";
import { ResultReveal } from "../components/ResultReveal";
import { SuspectPicker } from "../components/SuspectPicker";
import { TimelineItem, type TimelineStep } from "../components/TimelineItem";
import { useInvestigationEvents } from "../hooks/useInvestigationEvents";
import { useStoredProgress } from "../hooks/useStoredProgress";
import { ApiError, fetchCase, fetchInvestigationResult } from "../services/api";
import type {
  EvidenceView,
  InvestigationEvent,
  InvestigationResult,
  PublicCase,
} from "../types/api";
import type { SuspectPick } from "../types/progress";

// 공통 버튼 모양
const PRIMARY_BUTTON =
  "min-h-11 flex-1 rounded-lg bg-sky-600 px-4 font-semibold hover:bg-sky-500 disabled:cursor-not-allowed disabled:bg-slate-700";
const SECONDARY_BUTTON =
  "min-h-11 flex-1 rounded-lg bg-slate-700 px-4 font-semibold hover:bg-slate-600";

// 수사 화면
// 주소의 수사 ID로 수사 보기 화면을 그리며, 수사가 바뀌면 상태를 새로 시작하는 컴포넌트
export function InvestigationPage() {
  // 주소의 수사 ID
  const { investigationId = "" } = useParams();
  // 수사 ID마다 새로 그리기
  return (
    <InvestigationView
      key={investigationId}
      investigationId={investigationId}
    />
  );
}

// 타임라인 만들기
// 이벤트 목록을 순번별 도구 선택·가설·결과 단계 목록으로 묶는 함수
function buildTimeline(events: InvestigationEvent[]): TimelineStep[] {
  // 순번 → 단계
  const steps = new Map<number, TimelineStep>();
  // 순번에 해당하는 단계 꺼내기 (없으면 생성)
  const stepOf = (step: number): TimelineStep => {
    const existing = steps.get(step);
    if (existing) return existing;
    const created: TimelineStep = { step };
    steps.set(step, created);
    return created;
  };
  // 이벤트 종류별로 단계에 반영
  for (const event of events) {
    if (event.event === "tool_selected")
      stepOf(event.data.step).selected = event.data;
    if (event.event === "hypothesis_updated") {
      stepOf(event.data.step).hypothesis = event.data.hypothesis;
    }
    if (event.event === "evidence_found")
      stepOf(event.data.step).found = event.data;
  }
  // 순번 순서로 반환
  return [...steps.values()].sort((a, b) => a.step - b.step);
}

// 확보 증거 모으기
// 주어진 단계들의 결과 증거를 처음 나온 순서대로 중복 없이 모으는 함수
function collectEvidence(steps: TimelineStep[]): EvidenceView[] {
  // 증거 ID → 증거
  const collected = new Map<string, EvidenceView>();
  for (const item of steps) {
    for (const evidence of item.found?.evidence ?? []) {
      if (!collected.has(evidence.id)) collected.set(evidence.id, evidence);
    }
  }
  // 목록 반환
  return [...collected.values()];
}

// 수사 보기 속성
interface InvestigationViewProps {
  // 수사 ID
  investigationId: string;
}

// 수사 보기
// AI 조사를 한 단계씩 공개하고, 사용자가 범인을 고른 뒤 AI 수사가 끝나면 결론과 정답을 보여 주는 컴포넌트
function InvestigationView({ investigationId }: InvestigationViewProps) {
  // 수사 결과, 공개 사건 정보, 기록 없음, 불러오기 오류
  const [result, setResult] = useState<InvestigationResult | null>(null);
  const [publicCase, setPublicCase] = useState<PublicCase | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  // 화면 상태: 안내문 다시 보기, 범인 고르기 패널, 모바일 사건 정보 펼침
  const [guideOpen, setGuideOpen] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [caseInfoOpen, setCaseInfoOpen] = useState(false);
  // 저장되는 진행 상태
  const [progress, updateProgress] = useStoredProgress(investigationId);

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
  const { events, connection, done, reconnect } = useInvestigationEvents(
    result ? investigationId : null,
  );

  // 마지막 이벤트를 받으면 결과를 다시 조회 (화면에는 범인을 고른 뒤에만 사용)
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

  // 단계 묶기: 결과까지 도착한 단계만 완성된 단계
  const completedSteps = useMemo(
    () => buildTimeline(events).filter((item) => item.found),
    [events],
  );

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

  // 공개 단계: 저장된 수와 완성된 단계 수 중 작은 값까지만
  const revealedCount = Math.min(progress.revealedSteps, completedSteps.length);
  const revealed = completedSteps.slice(0, revealedCount);
  const current = revealed[revealed.length - 1];
  const previous = revealed.slice(0, -1);
  const evidence = collectEvidence(revealed);
  // 남은 예산: 마지막 공개 단계 기준 (0단계는 전체)
  const remaining = current?.found?.remaining_budget ?? result.tool_budget;
  // AI 조사 종료·오류 여부 (오류는 숨기지 않음)
  const aiFailed =
    events.some((event) => event.event === "error") ||
    (done && result.status === "failed");
  // 범인 선택 여부와 결과 공개 조건
  const picked = progress.pickedSuspect !== null;
  const canReveal =
    picked &&
    done &&
    !aiFailed &&
    (result.status === "completed" || result.status === "inconclusive");
  // 안내문 표시 여부 (처음이거나 다시 열었을 때)
  const showGuide = !progress.guideClosed || guideOpen;
  // 다음 단계가 있는지
  const hasNext = revealedCount < completedSteps.length;

  // 다음 단계 공개
  // 공개 단계 수를 하나 늘려 저장하는 함수
  function revealNext() {
    // 현재 공개 수 + 1
    updateProgress({ revealedSteps: revealedCount + 1 });
  }

  // 범인 확정
  // 고른 값과 고른 시점의 공개 단계 수를 저장하고 고르기 패널을 닫는 함수
  function confirmPick(pick: SuspectPick) {
    // 선택 저장 (이후 변경 불가)
    updateProgress({ pickedSuspect: pick, pickedAtStep: revealedCount });
    setPickerOpen(false);
  }

  // 안내문 닫기
  // 처음 안내문이면 닫음 여부를 저장하고, 다시 연 안내문이면 화면에서만 닫는 함수
  function closeGuide() {
    // 닫음 저장 후 다시 보기 상태 해제
    updateProgress({ guideClosed: true });
    setGuideOpen(false);
  }

  // 단계 조작 영역 (다음·범인 고르기·안내 문구)
  const controls = !picked && (
    <div className="space-y-3">
      {/* 다음 / 조사 중 / 조사 끝 안내 */}
      {hasNext ? (
        <div className="flex flex-col gap-2 sm:flex-row">
          <button type="button" onClick={revealNext} className={PRIMARY_BUTTON}>
            다음
          </button>
          {!aiFailed && (
            <button
              type="button"
              onClick={() => setPickerOpen(true)}
              className={SECONDARY_BUTTON}
            >
              범인 고르기
            </button>
          )}
        </div>
      ) : !done && !aiFailed ? (
        <div className="space-y-2">
          <div className="flex flex-col gap-2 sm:flex-row">
            <button type="button" disabled className={PRIMARY_BUTTON}>
              다음
            </button>
            <button
              type="button"
              onClick={() => setPickerOpen(true)}
              className={SECONDARY_BUTTON}
            >
              범인 고르기
            </button>
          </div>
          <p className="text-sm text-slate-400">AI가 조사 중이에요…</p>
        </div>
      ) : (
        !aiFailed && (
          <div className="space-y-2">
            <p className="text-sm text-slate-300">
              AI의 조사는 여기까지예요. 범인을 골라 주세요.
            </p>
            <button
              type="button"
              onClick={() => setPickerOpen(true)}
              className={`${SECONDARY_BUTTON} w-full`}
            >
              범인 고르기
            </button>
          </div>
        )
      )}
      {/* 범인 고르기 패널 */}
      {pickerOpen && !aiFailed && publicCase && (
        <SuspectPicker
          suspects={publicCase.suspects}
          onConfirm={confirmPick}
          onCancel={() => setPickerOpen(false)}
        />
      )}
    </div>
  );

  // 0단계 안내
  const emptyNotice = revealed.length === 0 && (
    <p className="text-sm text-slate-400">
      아직 공개한 단계가 없어요. &apos;다음&apos;을 눌러 AI의 첫 조사를
      확인하세요.
    </p>
  );

  // 오류 안내 (숨기지 않음)
  const failureNotice = aiFailed && (
    <div>
      <p className="text-sm text-red-400">AI 수사 중 오류가 발생했어요</p>
      <Link to="/" className="mt-2 inline-block text-sky-400 underline">
        사건 목록으로
      </Link>
    </div>
  );

  // 결과 공개 영역 (범인을 고른 뒤)
  const pickSection = picked && (
    <section className="space-y-3">
      {canReveal && progress.pickedSuspect !== null ? (
        <>
          <ResultReveal
            pick={progress.pickedSuspect}
            pickedAtStep={progress.pickedAtStep ?? 0}
            result={result}
            publicCase={publicCase}
          />
          {/* 남은 단계 모두 보기 */}
          {hasNext && (
            <button
              type="button"
              onClick={() =>
                updateProgress({ revealedSteps: completedSteps.length })
              }
              className={`${SECONDARY_BUTTON} w-full`}
            >
              남은 조사 단계도 모두 보기
            </button>
          )}
        </>
      ) : (
        !aiFailed && (
          <p className="text-sm text-amber-300">
            AI 수사가 끝나면 정답을 공개해요
          </p>
        )
      )}
    </section>
  );

  return (
    <PageContainer wide>
      {/* 목록으로 가기와 사건 제목 */}
      <Link to="/" className="text-sm text-sky-400 underline">
        ← 사건 목록
      </Link>
      <h1 className="mt-3 text-2xl font-bold">
        {publicCase?.title ?? result.case_id}
      </h1>

      <div className="mt-4 lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)] lg:gap-8">
        {/* PC 왼쪽: 사건 정보·가설 기록 (스크롤 시 고정) */}
        <aside className="hidden lg:block">
          <div className="sticky top-4 max-h-[calc(100vh-2rem)] space-y-6 overflow-y-auto pr-2">
            {publicCase && <CaseInfo publicCase={publicCase} />}
            <HypothesisLog steps={revealed} />
          </div>
        </aside>

        {/* 오른쪽(모바일은 전체) */}
        <div className="min-w-0 space-y-6">
          {/* 상태·예산·진행 방식 */}
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm text-slate-300">
              {done || aiFailed ? "AI 조사 종료" : "AI 조사 중"} · 남은 예산{" "}
              {remaining}/{result.tool_budget}
            </p>
            {progress.guideClosed && !guideOpen && (
              <button
                type="button"
                onClick={() => setGuideOpen(true)}
                className="min-h-11 rounded-lg border border-slate-700 px-3 text-sm hover:border-slate-500"
              >
                진행 방식
              </button>
            )}
          </div>

          {/* 연결 끊김 안내와 다시 연결 */}
          {!done && connection === "reconnecting" && (
            <p className="text-sm text-amber-300">
              연결이 끊겨 다시 연결하는 중이에요...
            </p>
          )}
          {!done && connection === "failed" && (
            <div>
              <p className="text-sm text-red-400">서버와 연결하지 못했어요.</p>
              <button
                type="button"
                onClick={reconnect}
                className="mt-2 min-h-11 rounded-lg bg-slate-700 px-4 text-sm font-medium hover:bg-slate-600"
              >
                다시 연결
              </button>
            </div>
          )}

          {/* 모바일: 사건 정보 접기/펼치기 */}
          {publicCase && (
            <div className="lg:hidden">
              <button
                type="button"
                onClick={() => setCaseInfoOpen((open) => !open)}
                className="min-h-11 w-full rounded-lg border border-slate-700 px-4 text-left text-sm hover:border-slate-500"
              >
                {caseInfoOpen ? "사건 정보 접기" : "사건 정보 펼치기"}
              </button>
              {caseInfoOpen && (
                <div className="mt-3">
                  <CaseInfo publicCase={publicCase} />
                </div>
              )}
            </div>
          )}

          {showGuide ? (
            // 안내문 (단계 자리)
            <GuidePanel
              firstTime={!progress.guideClosed}
              onClose={closeGuide}
            />
          ) : (
            <>
              {failureNotice}
              {/* 모바일: 현재 단계 → 버튼 → 지나온 단계 */}
              <div className="space-y-4 lg:hidden">
                {emptyNotice}
                {current && (
                  <ul>
                    <TimelineItem item={current} publicCase={publicCase} />
                  </ul>
                )}
                {controls}
                {previous.length > 0 && (
                  <ol className="space-y-2">
                    {previous.map((item) => (
                      <TimelineItem
                        key={item.step}
                        item={item}
                        publicCase={publicCase}
                      />
                    ))}
                  </ol>
                )}
              </div>
              {/* PC: 공개한 단계 전부 → 버튼 */}
              <div className="hidden space-y-4 lg:block">
                {emptyNotice}
                {revealed.length > 0 && (
                  <ol className="space-y-2">
                    {revealed.map((item) => (
                      <TimelineItem
                        key={item.step}
                        item={item}
                        publicCase={publicCase}
                      />
                    ))}
                  </ol>
                )}
                {controls}
              </div>
            </>
          )}

          {/* 모바일: 가설 기록 */}
          <div className="lg:hidden">
            <HypothesisLog steps={revealed} />
          </div>

          {/* 확보 증거 (공개 단계까지) */}
          <section>
            <h2 className="text-lg font-semibold">확보 증거</h2>
            <div className="mt-2">
              <EvidenceList items={evidence} />
            </div>
          </section>

          {/* 결과 공개 */}
          {pickSection}

          {/* 새 수사 */}
          <Link
            to="/"
            className="flex min-h-12 items-center justify-center rounded-lg bg-slate-700 px-4 font-semibold hover:bg-slate-600"
          >
            새 수사
          </Link>
        </div>
      </div>
    </PageContainer>
  );
}
