import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { PageContainer } from "../components/PageContainer";
import { DIFFICULTY_LABELS } from "../labels";
import { ApiError, fetchCase, startInvestigation } from "../services/api";
import type { PublicCase } from "../types/api";

// 이름과 설명 표기
// 설명이 있으면 "이름 - 설명", 없으면 이름만 반환하는 함수
function withDescription(name: string, description?: string | null): string {
  // 설명 유무에 따라 표기
  return description ? `${name} - ${description}` : name;
}

// 사건 상세 화면
// 사건 공개 정보를 보여 주고 수사 시작 버튼으로 수사를 시작해 수사 화면으로 이동하는 컴포넌트
export function CaseDetailPage() {
  // 주소의 사건 ID와 이동 함수
  const { caseId = "" } = useParams();
  const navigate = useNavigate();
  // 사건 정보, 사건을 찾을 수 없음 여부, 불러오기 오류
  const [publicCase, setPublicCase] = useState<PublicCase | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  // 수사 시작 요청 중 여부와 시작 오류
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  // 사건 ID가 바뀌면 사건 정보 불러오기
  useEffect(() => {
    // 언마운트 후 상태 변경 방지 플래그
    let active = true;
    fetchCase(caseId)
      .then((data) => {
        // 사건 정보 저장
        if (active) setPublicCase(data);
      })
      .catch((caught: unknown) => {
        if (!active) return;
        // 형식 오류·없는 사건은 찾을 수 없음 안내
        if (
          caught instanceof ApiError &&
          (caught.status === 400 || caught.status === 404)
        ) {
          setNotFound(true);
        } else {
          setLoadError(
            caught instanceof Error
              ? caught.message
              : "사건을 불러오지 못했어요.",
          );
        }
      });
    // 정리 함수
    return () => {
      active = false;
    };
  }, [caseId]);

  // 수사 시작
  // 수사 시작 요청을 보내고 성공하면 수사 화면으로 이동하는 함수 (요청 중 중복 시작 방지)
  async function handleStart() {
    // 요청 중이면 무시
    if (starting) return;
    setStarting(true);
    setStartError(null);
    try {
      // 시작 후 수사 화면으로 이동
      const started = await startInvestigation(caseId);
      navigate(`/investigations/${started.investigation_id}`);
    } catch (caught) {
      // 서버 안내 문장을 그대로 표시
      setStartError(
        caught instanceof Error ? caught.message : "수사를 시작하지 못했어요.",
      );
      setStarting(false);
    }
  }

  // 사건을 찾을 수 없을 때
  if (notFound) {
    return (
      <PageContainer>
        <p className="text-slate-300">사건을 찾을 수 없어요.</p>
        <Link to="/" className="mt-4 inline-block text-sky-400 underline">
          사건 목록으로
        </Link>
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      {/* 목록으로 가기 */}
      <Link to="/" className="text-sm text-sky-400 underline">
        ← 사건 목록
      </Link>

      {/* 불러오기 오류 */}
      {loadError && <p className="mt-6 text-sm text-red-400">{loadError}</p>}

      {/* 불러오는 중 */}
      {!publicCase && !loadError && (
        <p className="mt-6 text-sm text-slate-300">
          사건 정보를 불러오는 중...
        </p>
      )}

      {publicCase && (
        <>
          {/* 제목·난이도·예산 */}
          <h1 className="mt-4 text-2xl font-bold">{publicCase.title}</h1>
          <p className="mt-1 text-sm text-slate-400">
            {DIFFICULTY_LABELS[publicCase.difficulty]} · 조사 예산{" "}
            {publicCase.tool_budget}회
          </p>
          {/* 소개문 */}
          <p className="mt-4 leading-relaxed text-slate-200">
            {publicCase.introduction}
          </p>

          {/* 용의자 */}
          <section className="mt-6">
            <h2 className="text-lg font-semibold">용의자</h2>
            <ul className="mt-2 space-y-2">
              {publicCase.suspects.map((suspect) => (
                <li
                  key={suspect.id}
                  className="rounded-lg bg-slate-900 p-3 text-sm"
                >
                  <p className="font-medium">
                    {suspect.id} {suspect.name}{" "}
                    <span className="text-slate-400">({suspect.role})</span>
                  </p>
                  <p className="mt-1 text-slate-300">{suspect.description}</p>
                </li>
              ))}
            </ul>
          </section>

          {/* 장소 */}
          <section className="mt-6">
            <h2 className="text-lg font-semibold">장소</h2>
            <ul className="mt-2 space-y-1 text-sm text-slate-300">
              {publicCase.locations.map((location) => (
                <li key={location.id}>
                  {location.id}{" "}
                  {withDescription(location.name, location.description)}
                </li>
              ))}
            </ul>
          </section>

          {/* 카메라 */}
          <section className="mt-6">
            <h2 className="text-lg font-semibold">카메라</h2>
            <ul className="mt-2 space-y-2 text-sm text-slate-300">
              {publicCase.cameras.map((camera) => (
                <li key={camera.id}>
                  <p>
                    {camera.id}{" "}
                    {withDescription(camera.name, camera.description)}
                  </p>
                  <p className="text-xs text-slate-400">
                    조회 가능 시간대: {camera.time_windows.join(", ")}
                  </p>
                </li>
              ))}
            </ul>
          </section>

          {/* 질문 주제 */}
          <section className="mt-6">
            <h2 className="text-lg font-semibold">질문 주제</h2>
            <ul className="mt-2 space-y-1 text-sm text-slate-300">
              {publicCase.topics.map((topic) => (
                <li key={topic.id}>
                  {topic.id} {topic.name}
                </li>
              ))}
            </ul>
          </section>

          {/* 수사 시작 */}
          <div className="mt-8">
            <button
              type="button"
              onClick={() => void handleStart()}
              disabled={starting}
              className="min-h-12 w-full rounded-lg bg-sky-600 px-4 font-semibold hover:bg-sky-500 disabled:cursor-not-allowed disabled:bg-slate-700"
            >
              {starting ? "수사를 시작하는 중..." : "수사 시작"}
            </button>
            {/* 시작 실패 안내 (서버 문장 그대로) */}
            {startError && (
              <p className="mt-3 text-sm text-red-400">{startError}</p>
            )}
          </div>
        </>
      )}
    </PageContainer>
  );
}
