import type { PublicCase } from "../types/api";

// 사건 정보 속성
interface CaseInfoProps {
  // 공개 사건 정보
  publicCase: PublicCase;
}

// 이름과 설명 표기
// 설명이 있으면 "이름 - 설명", 없으면 이름만 반환하는 함수
function withDescription(name: string, description?: string | null): string {
  // 설명 유무에 따라 표기
  return description ? `${name} - ${description}` : name;
}

// 사건 정보
// 사건 소개·용의자·장소·카메라·질문 주제를 보여 주는 컴포넌트
export function CaseInfo({ publicCase }: CaseInfoProps) {
  return (
    <div className="space-y-4 text-sm">
      {/* 소개문 */}
      <p className="leading-relaxed text-slate-200">
        {publicCase.introduction}
      </p>
      {/* 용의자 */}
      <section>
        <h3 className="font-semibold">용의자</h3>
        <ul className="mt-1 space-y-1 text-slate-300">
          {publicCase.suspects.map((suspect) => (
            <li key={suspect.id}>
              {suspect.id} {suspect.name} ({suspect.role}) -{" "}
              {suspect.description}
            </li>
          ))}
        </ul>
      </section>
      {/* 장소 */}
      <section>
        <h3 className="font-semibold">장소</h3>
        <ul className="mt-1 space-y-1 text-slate-300">
          {publicCase.locations.map((location) => (
            <li key={location.id}>
              {location.id}{" "}
              {withDescription(location.name, location.description)}
            </li>
          ))}
        </ul>
      </section>
      {/* 카메라 */}
      <section>
        <h3 className="font-semibold">카메라</h3>
        <ul className="mt-1 space-y-1 text-slate-300">
          {publicCase.cameras.map((camera) => (
            <li key={camera.id}>
              {camera.id} {withDescription(camera.name, camera.description)} (
              {camera.time_windows.join(", ")})
            </li>
          ))}
        </ul>
      </section>
      {/* 질문 주제 */}
      <section>
        <h3 className="font-semibold">질문 주제</h3>
        <ul className="mt-1 space-y-1 text-slate-300">
          {publicCase.topics.map((topic) => (
            <li key={topic.id}>
              {topic.id} {topic.name}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
