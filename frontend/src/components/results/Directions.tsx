import { ChevronDown, CornerUpLeft, CornerUpRight, Flag, MoveUp, Navigation } from "lucide-react";
import { useState } from "react";
import type { RouteLeg, RouteStep } from "../../api/types";
import { duration, miles } from "../../lib/format";

const PREVIEW_STEPS = 6;

export default function Directions({ legs }: { legs: RouteLeg[] }) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {legs.map((leg, i) => (
        <LegDirections key={i} leg={leg} index={i} />
      ))}
    </div>
  );
}

function LegDirections({ leg, index }: { leg: RouteLeg; index: number }) {
  const [expanded, setExpanded] = useState(false);
  const steps = leg.steps.filter((s) => s.distance_miles > 0 || s.maneuver === "arrive");
  const shown = expanded ? steps : steps.slice(0, PREVIEW_STEPS);
  return (
    <div className="rounded-xl border border-mist-200">
      <div className="border-b border-mist-200 bg-mist-50/70 px-4 py-3">
        <p className="text-[11.5px] font-semibold tracking-wide text-slate-500 uppercase">
          Leg {index + 1} · {index === 0 ? "to pickup" : "loaded to drop-off"}
        </p>
        <p className="mt-0.5 text-[14px] font-semibold text-slate-900">
          {leg.from} → {leg.to}
        </p>
        <p className="text-[12.5px] text-slate-600">
          {leg.distance_miles > 0 ? `${miles(leg.distance_miles)} · ${duration(leg.drive_minutes)} driving` : "Already at the pickup"}
          {leg.summary && ` · via ${leg.summary}`}
        </p>
      </div>
      {leg.distance_miles > 0 && (
        <>
          <ol className="divide-y divide-mist-100">
            {shown.map((step, i) => (
              <li key={i} className="flex items-start gap-3 px-4 py-2.5">
                <StepIcon step={step} />
                <span className="flex-1 text-[13px] text-slate-700">{step.instruction}</span>
                {step.distance_miles > 0 && (
                  <span className="shrink-0 text-[12px] text-slate-500 tabular-nums">
                    {step.distance_miles < 0.2 ? `${Math.round(step.distance_miles * 5280)} ft` : `${step.distance_miles.toFixed(1)} mi`}
                  </span>
                )}
              </li>
            ))}
          </ol>
          {steps.length > PREVIEW_STEPS && (
            <button
              type="button"
              onClick={() => setExpanded((e) => !e)}
              className="flex w-full items-center justify-center gap-1 border-t border-mist-200 py-2.5 text-[12.5px] font-semibold text-ink-700 hover:bg-mist-50"
            >
              {expanded ? "Show fewer steps" : `Show all ${steps.length} steps`}
              <ChevronDown className={`size-4 transition ${expanded ? "rotate-180" : ""}`} />
            </button>
          )}
        </>
      )}
    </div>
  );
}

function StepIcon({ step }: { step: RouteStep }) {
  const text = step.instruction.toLowerCase();
  const Icon =
    step.maneuver === "arrive" ? Flag
    : step.maneuver === "depart" ? Navigation
    : text.includes("left") ? CornerUpLeft
    : text.includes("right") ? CornerUpRight
    : MoveUp;
  return (
    <span className="mt-0.5 grid size-6 shrink-0 place-items-center rounded-full bg-mist-100 text-ink-800">
      <Icon className="size-3.5" />
    </span>
  );
}
