/// <reference types="vite/client" />

// 프론트엔드 환경변수 타입
// Vite가 주입하는 환경변수의 이름과 타입을 선언하는 인터페이스
interface ImportMetaEnv {
  // 백엔드 API 기본 URL
  readonly VITE_API_BASE_URL: string;
}

// import.meta 타입
// import.meta.env가 위 환경변수 타입을 갖도록 확장하는 인터페이스
interface ImportMeta {
  // 환경변수 객체
  readonly env: ImportMetaEnv;
}
