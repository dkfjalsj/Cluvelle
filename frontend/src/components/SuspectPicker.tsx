import { useState } from "react";

import type { Suspect } from "../types/api";
import { UNKNOWN_PICK, type SuspectPick } from "../types/progress";

// 범인 고르기 속성
interface SuspectPickerProps {
  // 용의자 목록
  suspects: Suspect[];
  // 확정 처리 (고른 값 전달)
  onConfirm: (pick: SuspectPick) => void;
  // 취소 처리
  onCancel: () => void;
}

// 범인 고르기 패널
// 용의자 3명과 "모르겠어요" 중 하나를 고르고 "이 사람으로 결정"으로 확정하는 컴포넌트
export function SuspectPicker({
  suspects,
  onConfirm,
  onCancel,
}: SuspectPickerProps) {
  // 지금 고른 값 (확정 전)
  const [selected, setSelected] = useState<SuspectPick | null>(null);
  // 선택지 목록 (용의자 + 모르겠어요)
  const options = [
    ...suspects.map((suspect) => ({
      value: suspect.id,
      label: `${suspect.id} ${suspect.name} (${suspect.role})`,
    })),
    { value: UNKNOWN_PICK, label: "모르겠어요" },
  ];
  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900 p-4">
      {/* 선택지 (하나만 선택) */}
      <div className="space-y-2" role="radiogroup">
        {options.map((option) => (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={selected === option.value}
            onClick={() => setSelected(option.value)}
            className={`min-h-11 w-full rounded-lg border px-4 text-left text-sm ${
              selected === option.value
                ? "border-amber-400 bg-slate-800 text-amber-200"
                : "border-slate-700 hover:border-slate-500"
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>
      {/* 확정·취소 */}
      <div className="mt-4 flex flex-col gap-2 sm:flex-row">
        <button
          type="button"
          disabled={selected === null}
          onClick={() => selected && onConfirm(selected)}
          className="min-h-11 flex-1 rounded-lg bg-amber-600 px-4 font-semibold hover:bg-amber-500 disabled:cursor-not-allowed disabled:bg-slate-700"
        >
          이 사람으로 결정
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="min-h-11 flex-1 rounded-lg bg-slate-700 px-4 font-semibold hover:bg-slate-600"
        >
          취소
        </button>
      </div>
    </div>
  );
}
