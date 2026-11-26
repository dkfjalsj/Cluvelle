// 로고 속성
interface LogoProps {
  // 한 변 크기(px)
  size?: number;
}

// 로고
// 어두운 남색 둥근 배경 위 호박색 돋보기(렌즈 안 단서 점)를 인라인 SVG로 그리는 컴포넌트
export function Logo({ size = 28 }: LogoProps) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 32 32"
      width={size}
      height={size}
      aria-hidden="true"
      className="shrink-0"
    >
      {/* 둥근 배경 */}
      <rect width="32" height="32" rx="7" fill="#172554" />
      {/* 돋보기 렌즈 */}
      <circle
        cx="13.5"
        cy="13.5"
        r="7"
        fill="none"
        stroke="#f59e0b"
        strokeWidth="3.5"
      />
      {/* 돋보기 손잡이 */}
      <line
        x1="18.8"
        y1="18.8"
        x2="25.5"
        y2="25.5"
        stroke="#f59e0b"
        strokeWidth="4"
        strokeLinecap="round"
      />
      {/* 렌즈 안 단서 점 */}
      <circle cx="13.5" cy="13.5" r="2.2" fill="#f59e0b" />
    </svg>
  );
}
