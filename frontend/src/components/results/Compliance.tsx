import { CircleCheck, CircleX, Info } from "lucide-react";
import type { ComplianceCheck, TripPlan } from "../../api/types";
import { hhmm } from "../../lib/format";

export default function Compliance({ plan }: { plan: TripPlan }) {
  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <div>
        <ul className="space-y-3">
          {plan.compliance.checks.map((check) => (
            <CheckRow key={check.id} check={check} />
          ))}
        </ul>
        <p className="mt-4 flex gap-2 rounded-xl bg-mist-50 px-3.5 py-3 text-[12.5px] leading-relaxed text-slate-600">
          <Info className="mt-0.5 size-4 shrink-0 text-ink-700" />
          <span>
            The 11- and 14-hour limits run per duty period (between 10-hour breaks), not per calendar day, so one log
            sheet can legitimately show more than 11 hours of driving across two duty periods. On-duty work after the
            14th hour or past 70 hours is allowed; only driving is not (FMCSA guide, pp. 9–11). This audit re-derives
            every clock from the final timeline, independently of the planner.
          </span>
        </p>
      </div>
      <div>
        <h3 className="mb-2 text-[13px] font-semibold text-slate-800">Assumptions</h3>
        <ul className="space-y-2 text-[12.5px] leading-relaxed text-slate-600">
          {plan.assumptions.map((a) => (
            <li key={a} className="flex gap-2">
              <span className="mt-[7px] size-1.5 shrink-0 rounded-full bg-ink-700/60" />
              {a}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function CheckRow({ check }: { check: ComplianceCheck }) {
  const fmt = (v: number) => (check.unit === "minutes" ? hhmm(v) : check.unit === "miles" ? `${Math.round(v).toLocaleString()} mi` : String(v));
  const ratio = check.unit === "gaps" ? (check.passed ? 0 : 1) : check.limit ? check.actual / check.limit : 0;
  return (
    <li className="rounded-xl border border-mist-200 px-3.5 py-3">
      <div className="flex items-center gap-2.5">
        {check.passed ? <CircleCheck className="size-5 shrink-0 text-emerald-600" /> : <CircleX className="size-5 shrink-0 text-coral-600" />}
        <span className="flex-1 text-[13.5px] font-semibold text-slate-800">{check.label}</span>
        {check.unit !== "gaps" && (
          <span className="text-[12.5px] text-slate-600 tabular-nums">
            <span className="font-semibold text-slate-900">{fmt(check.actual)}</span> / {fmt(check.limit)}
          </span>
        )}
      </div>
      {check.unit !== "gaps" && (
        <div className="mt-2 ml-7.5 h-1.5 overflow-hidden rounded-full bg-mist-100">
          <div
            className={`h-full rounded-full ${check.passed ? "bg-emerald-500" : "bg-coral-500"}`}
            style={{ width: `${Math.min(100, ratio * 100)}%` }}
          />
        </div>
      )}
      <p className="mt-1.5 ml-7.5 text-[12px] text-slate-500">{check.detail}</p>
    </li>
  );
}
