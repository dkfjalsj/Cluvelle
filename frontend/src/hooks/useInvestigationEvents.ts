import { useCallback, useEffect, useRef, useState } from "react";

import { buildEventStreamUrl } from "../services/api";
import type { InvestigationEvent, InvestigationEventType } from "../types/api";

// 받는 이벤트 종류
const EVENT_TYPES: InvestigationEventType[] = [
  "tool_selected",
  "hypothesis_updated",
  "evidence_found",
  "finished",
  "error",
];
// 스트림을 닫는 마지막 이벤트 종류
const TERMINAL_TYPES: InvestigationEventType[] = ["finished", "error"];
// 다시 연결 대기 시간(ms)과 최대 횟수
const RECONNECT_DELAY_MS = 2000;
const MAX_RECONNECT_ATTEMPTS = 5;

// 연결 상태
export type ConnectionState =
  "idle" | "connecting" | "open" | "reconnecting" | "failed" | "closed";

// 이벤트 훅 결과
// 받은 이벤트 목록·연결 상태·종료 여부·수동 재연결 함수를 담는 타입
export interface InvestigationEventsState {
  // 번호 순서로 정렬된 이벤트 (중복 없음)
  events: InvestigationEvent[];
  // 연결 상태
  connection: ConnectionState;
  // finished 또는 error를 받았는지
  done: boolean;
  // 자동 재연결이 모두 실패한 뒤 다시 연결하는 함수
  reconnect: () => void;
}

// 수사 이벤트 훅
// 수사 이벤트 스트림에 연결해 이벤트를 모으고, 마지막 이벤트 뒤 직접 닫으며, 끊기면 이어 받기로 재연결하는 커스텀 훅
export function useInvestigationEvents(
  investigationId: string | null,
): InvestigationEventsState {
  // 이벤트·연결 상태·종료 여부
  const [events, setEvents] = useState<InvestigationEvent[]>([]);
  const [connection, setConnection] = useState<ConnectionState>("idle");
  const [done, setDone] = useState(false);
  // 현재 연결, 재연결 타이머, 재연결 횟수, 마지막 번호, 받은 번호, 종료 여부
  const sourceRef = useRef<EventSource | null>(null);
  const timerRef = useRef<number | null>(null);
  const attemptsRef = useRef(0);
  const lastIdRef = useRef<number | null>(null);
  const seenRef = useRef<Set<number>>(new Set());
  const doneRef = useRef(false);
  // 재연결 타이머에서 부를 연결 함수 (자기 자신을 직접 참조하지 않기 위함)
  const connectRef = useRef<(id: string) => void>(() => undefined);

  // 연결 정리
  // 현재 연결을 닫고 예약된 재연결 타이머를 해제하는 함수
  const cleanup = useCallback(() => {
    // 연결 닫기
    sourceRef.current?.close();
    sourceRef.current = null;
    // 타이머 해제
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  // 스트림 연결
  // 마지막으로 받은 번호 다음부터 스트림에 연결하고 이벤트·오류 처리기를 다는 함수
  const connect = useCallback(
    (id: string) => {
      // 이전 연결 정리 후 새 연결
      cleanup();
      const source = new EventSource(
        buildEventStreamUrl(id, lastIdRef.current),
      );
      sourceRef.current = source;

      // 연결되면 재연결 횟수 초기화
      source.onopen = () => {
        attemptsRef.current = 0;
        setConnection("open");
      };

      // 이벤트 종류별 처리기
      for (const type of EVENT_TYPES) {
        source.addEventListener(type, (message: MessageEvent<string>) => {
          // 이벤트 번호 (같은 번호는 한 번만 반영)
          const eventId = Number(message.lastEventId);
          if (!Number.isInteger(eventId) || seenRef.current.has(eventId)) {
            return;
          }
          seenRef.current.add(eventId);
          lastIdRef.current = Math.max(lastIdRef.current ?? -1, eventId);
          // 이벤트 객체 만들어 번호 순서로 추가
          const event = {
            id: eventId,
            event: type,
            data: JSON.parse(message.data) as unknown,
          } as InvestigationEvent;
          setEvents((prev) => [...prev, event].sort((a, b) => a.id - b.id));
          // 마지막 이벤트면 직접 닫고 종료 표시
          if (TERMINAL_TYPES.includes(type)) {
            doneRef.current = true;
            cleanup();
            setConnection("closed");
            setDone(true);
          }
        });
      }

      // 연결 오류: 닫고 2초 뒤 이어 받기로 재연결 (최대 5번)
      source.onerror = () => {
        // 이미 끝났으면 무시
        if (doneRef.current) return;
        cleanup();
        if (attemptsRef.current < MAX_RECONNECT_ATTEMPTS) {
          attemptsRef.current += 1;
          setConnection("reconnecting");
          timerRef.current = window.setTimeout(
            () => connectRef.current(id),
            RECONNECT_DELAY_MS,
          );
        } else {
          // 모두 실패
          setConnection("failed");
        }
      };
    },
    [cleanup],
  );

  // 재연결 타이머가 부를 최신 연결 함수 보관
  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  // 수사 ID가 정해지면 처음부터 연결, 바뀌거나 사라지면 정리
  useEffect(() => {
    // 수사 ID가 없으면 연결하지 않음
    if (!investigationId) return;
    // 새 수사 기준으로 내부 값 초기화
    attemptsRef.current = 0;
    lastIdRef.current = null;
    seenRef.current = new Set();
    doneRef.current = false;
    connect(investigationId);
    // 정리: 연결·타이머 해제
    return cleanup;
  }, [investigationId, connect, cleanup]);

  // 수동 재연결
  // 재연결 횟수를 초기화하고 마지막 번호 다음부터 다시 연결하는 함수
  const reconnect = useCallback(() => {
    // 수사 ID가 없거나 이미 끝났으면 무시
    if (!investigationId || doneRef.current) return;
    attemptsRef.current = 0;
    setConnection("reconnecting");
    connect(investigationId);
  }, [investigationId, connect]);

  // 결과 반환
  return { events, connection, done, reconnect };
}
