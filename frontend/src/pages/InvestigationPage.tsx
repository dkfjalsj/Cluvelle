import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router";

import { EvidenceList } from "../components/EvidenceList";
import { GradingView } from "../components/GradingView";
import { PageContainer } from "../components/PageContainer";
import { ReportView } from "../components/ReportView";
import { TimelineItem, type TimelineStep } from "../components/TimelineItem";
import { useInvestigationEvents } from "../hooks/useInvestigationEvents";
import { STATUS_LABELS } from "../labels";
import { ApiError, fetchCase, fetchInvestigationResult } from "../services/api";
import type {
  EvidenceView,
  InvestigationEvent,
  InvestigationResult,
  PublicCase,
  RunStatus,
} from "../types/api";

// 종료 상태
const FINISHED_STATUSES: RunStatus[] = ["completed", "inconclusive", "failed"];

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
    if (event.event === "hypothesis_updated")
      stepOf(event.data.step).hypothesis = event.data.hypothesis;
    if (event.event === "evidence_found")
      stepOf(event.data.step).found = event.data;
  }
  // 순번 순서로 반환
  return [...steps.values()].sort((a, b) => a.step - b.step);
}

// 확보 증거 모으기
// 결과 이벤트들의 증거를 처음 나온 순서대로 중복 없이 모으는 함수
function collectEvidence(events: InvestigationEvent[]): EvidenceView[] {
  // 증거 ID → 증거
  const collected = new Map<string, EvidenceView>();
  for (const event of events) {
    if (event.event !== "evidence_found") continue;
    for (const item of event.data.evidence) {
      if (!collected.has(item.id)) collected.set(item.id, item);
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
// 결과·사건 정보를 불러오고 이벤트 스트림으로 실시간 타임라인을 그린 뒤 종료 후 보고서·정답을 보여 주는 컴포넌트
function InvestigationView({ investigationId }: InvestigationViewProps) {
  // 수사 결과, 공개 사건 정보, 기록 없음, 불러오기 오류, 정답 보기 여부
  const [result, setResult] = useState<InvestigationResult | null>(null);
  const [publicCase, setPublicCase] = useState<PublicCase | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [showGrading, setShowGrading] = useState(false);

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

  // 마지막 이벤트를 받으면 결과를 다시 조회해 보고서·채점 반영
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

  // 이벤트로 만든 타임라인·확보 증거·현재 가설·남은 예산·스트림 오류
  const timeline = useMemo(() => buildTimeline(events), [events]);
  const evidence = useMemo(() => collectEvidence(events), [events]);
  const currentHypothesis = useMemo(() => {
    const updates = events.filter(
      (event) => event.event === "hypothesis_updated",
    );
    const last = updates[updates.length - 1];
    return last && last.event === "hypothesis_updated"
      ? last.data.hypothesis
      : null;
  }, [events]);
  const lastFound = [...events]
    .reverse()
    .find((event) => event.event === "evidence_found");
  const streamError = events.find((event) => event.event === "error");

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

  // 종료 여부와 진행 상태 표시
  const finished = FINISHED_STATUSES.includes(result.status);
  const disconnected = connection === "reconnecting" || connection === "failed";
  const statusText = finished
    ? STATUS_LABELS[result.status]
    : disconnected
      ? "연결 끊김"
      : "진행 중";
  // 남은 예산 (마지막 결과 이벤트 기준, 없으면 결과 기준)
  const remaining =
    lastFound && lastFound.event === "evidence_found"
      ? lastFound.data.remaining_budget
      : result.tool_budget - result.tool_call_count;

  return (
    <PageContainer>
      {/* 상단: 사건 제목·진행 상태·남은 예산 */}
      <Link to="/" className="text-sm text-sky-400 underline">
        ← 사건 목록
      </Link>
      <h1 className="mt-4 text-2xl font-bold">
        {publicCase?.title ?? result.case_id}
      </h1>
      <p className="mt-1 text-sm text-slate-300">
        상태: <span className="font-medium">{statusText}</span> · 남은 예산{" "}
        {remaining}/{result.tool_budget}
      </p>

      {/* 연결 끊김 안내와 다시 연결 */}
      {!finished && connection === "reconnecting" && (
        <p className="mt-2 text-sm text-amber-300">
          연결이 끊겨 다시 연결하는 중이에요...
        </p>
      )}
      {!finished && connection === "failed" && (
        <div className="mt-2">
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

      {/* 현재 가설 */}
      <section className="mt-6">
        <h2 className="text-lg font-semibold">현재 가설</h2>
        <p className="mt-1 text-sm text-amber-200">
          {currentHypothesis ?? "아직 가설이 없어요."}
        </p>
      </section>

      {/* 조사 타임라인 */}
      <section className="mt-6">
        <h2 className="text-lg font-semibold">조사 타임라인</h2>
        {timeline.length === 0 ? (
          <p className="mt-2 text-sm text-slate-400">
            AI 탐정이 첫 조사를 고르는 중이에요...
          </p>
        ) : (
          <ol className="mt-2 space-y-2">
            {timeline.map((item) => (
              <TimelineItem
                key={item.step}
                item={item}
                publicCase={publicCase}
              />
            ))}
          </ol>
        )}
        {/* 스트림 오류 문장 */}
        {streamError && streamError.event === "error" && (
          <p className="mt-2 text-sm text-red-400">
            {streamError.data.message}
          </p>
        )}
      </section>

      {/* 확보 증거 */}
      <section className="mt-6">
        <h2 className="text-lg font-semibold">확보 증거</h2>
        <div className="mt-2">
          <EvidenceList items={evidence} />
        </div>
      </section>

      {/* 종료 후: 오류·보고서·정답 보기 */}
      {finished && (
        <>
          {result.error && (
            <p className="mt-6 text-sm text-red-400">{result.error}</p>
          )}
          <section className="mt-6">
            <h2 className="text-lg font-semibold">최종 보고서</h2>
            <div className="mt-2">
              {result.final_report ? (
                <ReportView
                  report={result.final_report}
                  reportStatus={result.report_status}
                  publicCase={publicCase}
                />
              ) : (
                <p className="text-sm text-slate-400">보고서가 없어요.</p>
              )}
            </div>
          </section>

          {result.grading && (
            <section className="mt-6">
              {showGrading ? (
                <GradingView grading={result.grading} />
              ) : (
                <button
                  type="button"
                  onClick={() => setShowGrading(true)}
                  className="min-h-12 w-full rounded-lg bg-amber-600 px-4 font-semibold hover:bg-amber-500"
                >
                  정답 보기
                </button>
              )}
            </section>
          )}
        </>
      )}

      {/* 새 수사 */}
      <Link
        to="/"
        className="mt-8 flex min-h-12 items-center justify-center rounded-lg bg-slate-700 px-4 font-semibold hover:bg-slate-600"
      >
        새 수사
      </Link>
    </PageContainer>
  );
}
