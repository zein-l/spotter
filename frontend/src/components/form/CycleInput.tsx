import clsx from "clsx";
import { useId } from "react";

interface Props {
  value: string;
  onChange: (value: string) => void;
  error?: string | null;
}

export default function CycleInput({ value, onChange, error }: Props) {
  const id = useId();
  const hours = Number(value);
  const valid = value.trim() !== "" && Number.isFinite(hours) && hours >= 0 && hours <= 70;
  const used = valid ? hours : 0;
  const left = 70 - used;
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between">
        <label htmlFor={id} className="text-[13px] font-semibold text-slate-700">
          Current cycle used
        </label>
        <span className={clsx("text-[12px] font-medium tabular-nums", left < 11 ? "text-coral-600" : "text-slate-500")}>
          {valid ? `${left.toFixed(left % 1 ? 1 : 0)} h left of 70` : "0–70 hours"}
        </span>
      </div>
      <div className="flex items-center gap-3">
        <input
          type="range"
          min={0}
          max={70}
          step={0.5}
          value={used}
          onChange={(event) => onChange(event.target.value)}
          className="h-2 flex-1 cursor-pointer accent-ink-800"
          aria-label="Current cycle used (hours)"
        />
        <div className="relative w-24">
          <input
            id={id}
            type="number"
            inputMode="decimal"
            min={0}
            max={70}
            step={0.25}
            value={value}
            onChange={(event) => onChange(event.target.value)}
            className={clsx("input pr-8 text-right tabular-nums", error && "input-error")}
            aria-invalid={Boolean(error)}
          />
          <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-sm text-slate-400">h</span>
        </div>
      </div>
      {error ? (
        <p className="mt-1.5 text-[12.5px] font-medium text-coral-600">{error}</p>
      ) : (
        <p className="mt-1.5 text-[12px] text-slate-500">On-duty hours already used in the 70-hour / 8-day cycle.</p>
      )}
    </div>
  );
}
