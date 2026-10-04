import { CalendarDays, Gauge, ShieldCheck, ShieldX, Timer, Waypoints } from "lucide-react";
import type { ReactNode } from "react";
import type { TripPlan } from "../../api/types";
import { clock, dayLabel, duration, hours, miles } from "../../lib/format";

export default function SummaryCards({ plan, onShowCompliance }: { plan: TripPlan; onShowCompliance: () => void }) {
  const s = plan.summary;
  const cycleEnd = s.cycle_used_end_minutes;
  const failed = plan.compliance.checks.filter((c) => !c.passed).length;
  const stops = [
    s.fuel_stops && `${s.fuel_stops} fuel`,
    s.breaks && `${s.breaks} break${s.breaks > 1 ? "s" : ""}`,
    s.rests && `${s.rests} rest${s.rests > 1 ? "s" : ""}`,
    s.restarts && `${s.restarts} restart`,
  ].filter(Boolean);

  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-3 2xl:grid-cols-6">
      <Card icon={<Waypoints />} label="Distance" value={miles(s.total_miles)} sub={`${plan.route.legs[0].distance_miles.toFixed(0)} mi to pickup`} />
      <Card icon={<Gauge />} label="Driving" value={duration(s.driving_minutes)} sub={`avg ${s.average_speed_mph} mph, truck-capped`} />
      <Card
        icon={<Timer />}
        label="Trip time"
        value={duration(s.total_minutes, { days: true })}
        sub={`Delivered ${dayLabel(s.dropoff_arrival)}, ${clock(s.dropoff_arrival)}`}
      />
      <Card
        icon={<CalendarDays />}
        label="Daily logs"
        value={`${s.log_days} sheet${s.log_days > 1 ? "s" : ""}`}
        sub={stops.length ? stops.join(" · ") : "No rests needed"}
      />
      <Card
        icon={<Gauge />}
        label="70-hour cycle"
        value={`${hours(cycleEnd)} h`}
        sub={`was ${hours(s.cycle_used_start_minutes)} h · ${hours(s.cycle_available_end_minutes)} h left`}
        meter={cycleEnd / 4200}
      />
      <button type="button" onClick={onShowCompliance} className="text-left">
        <Card
          icon={failed ? <ShieldX /> : <ShieldCheck />}
          label="HOS compliance"
          value={failed ? `${failed} issue${failed > 1 ? "s" : ""}` : "Compliant"}
          sub={`${plan.compliance.checks.length - failed}/${plan.compliance.checks.length} checks passed`}
          tone={failed ? "bad" : "good"}
        />
      </button>
    </div>
  );
}

function Card(props: { icon: ReactNode; label: string; value: string; sub: string; meter?: number; tone?: "good" | "bad" }) {
  const toneClass =
    props.tone === "good" ? "text-emerald-700 [&_svg]:text-emerald-600" : props.tone === "bad" ? "text-coral-600 [&_svg]:text-coral-600" : "";
  return (
    <div className="card h-full px-4 py-3.5">
      <div className={`flex items-center gap-1.5 text-[12px] font-semibold text-slate-500 [&_svg]:size-3.5 [&_svg]:text-slate-400 ${toneClass}`}>
        {props.icon}
        {props.label}
      </div>
      <div className={`mt-1 text-[22px] leading-tight font-bold tracking-tight text-slate-900 tabular-nums ${toneClass}`}>{props.value}</div>
      {props.meter !== undefined && (
        <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-mist-100">
          <div
            className={`h-full rounded-full ${props.meter > 0.85 ? "bg-coral-500" : "bg-ink-700"}`}
            style={{ width: `${Math.min(100, props.meter * 100)}%` }}
          />
        </div>
      )}
      <div className="mt-1 truncate text-[12px] text-slate-500" title={props.sub}>
        {props.sub}
      </div>
    </div>
  );
}
