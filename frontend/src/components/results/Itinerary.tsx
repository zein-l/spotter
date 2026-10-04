import clsx from "clsx";
import { ArrowDown } from "lucide-react";
import { Fragment, useMemo } from "react";
import type { Stop, TripPlan } from "../../api/types";
import { clock, dayLabel, duration, miles } from "../../lib/format";
import { STOP_STYLE, WAYPOINT_STYLE } from "../../lib/stopStyles";

type Row =
  | { kind: "stop"; stop: Stop; day: string }
  | { kind: "drive"; start: string; end: string; minutes: number; miles: number; via: string; day: string };

interface Props {
  plan: TripPlan;
  selectedStop: number | null;
  onSelectStop: (index: number) => void;
}

export default function Itinerary({ plan, selectedStop, onSelectStop }: Props) {
  const rows = useMemo(() => buildRows(plan), [plan]);
  const dayNumbers = new Map(plan.daily_logs.map((log) => [log.date, log.day]));

  return (
    <ol className="relative">
      {rows.map((row, i) => {
        const newDay = i === 0 || rows[i - 1].day !== row.day;
        return (
          <Fragment key={i}>
            {newDay && (
              <li className="sticky top-0 z-10 -mx-1 bg-white/95 px-1 pt-3 pb-2 backdrop-blur first:pt-0">
                <span className="rounded-full bg-mist-100 px-2.5 py-1 text-[11.5px] font-semibold text-ink-900">
                  Day {dayNumbers.get(row.day) ?? "?"} · {dayLabel(row.day)}
                </span>
              </li>
            )}
            {row.kind === "drive" ? <DriveRow row={row} /> : <StopRow stop={row.stop} selected={selectedStop === row.stop.index} onSelect={onSelectStop} />}
          </Fragment>
        );
      })}
    </ol>
  );
}

function StopRow({ stop, selected, onSelect }: { stop: Stop; selected: boolean; onSelect: (index: number) => void }) {
  const style = stop.waypoint && stop.type === "start" ? WAYPOINT_STYLE[stop.waypoint] : STOP_STYLE[stop.type];
  const Icon = style.icon;
  const title = stop.type === "start" ? "Depart" : stop.title;
  return (
    <li>
      <button
        type="button"
        onClick={() => onSelect(stop.index)}
        className={clsx(
          "flex w-full gap-3 rounded-xl px-2 py-2.5 text-left transition",
          selected ? "bg-mist-100 ring-1 ring-ink-700/20" : "hover:bg-mist-50",
        )}
      >
        <span className="grid size-8 shrink-0 place-items-center rounded-full text-white shadow-sm" style={{ background: style.color }}>
          <Icon className="size-4" strokeWidth={2.2} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex items-baseline justify-between gap-2">
            <span className="truncate text-[14px] font-semibold text-slate-900">{title}</span>
            <span className="shrink-0 text-[12.5px] font-medium text-slate-600 tabular-nums">
              {clock(stop.arrival)}
              {stop.minutes > 0 && <> – {clock(stop.departure)}</>}
            </span>
          </span>
          <span className="block truncate text-[12.5px] text-slate-500">{stop.place_detail}</span>
          <span className="mt-1 flex flex-wrap gap-1">
            {stop.activities.map((a, i) => (
              <span key={i} className="rounded-md px-1.5 py-0.5 text-[11.5px] font-medium" style={{ background: style.soft, color: "#334155" }}>
                {a.label} · {duration(a.minutes)}
              </span>
            ))}
          </span>
        </span>
      </button>
    </li>
  );
}

function DriveRow({ row }: { row: Extract<Row, { kind: "drive" }> }) {
  return (
    <li className="flex items-center gap-3 py-1 pl-[19px]">
      <span className="h-9 w-0.5 rounded bg-duty-d/70" aria-hidden />
      <span className="flex items-center gap-1.5 text-[12.5px] text-slate-600">
        <ArrowDown className="size-3.5 text-duty-d" />
        <span className="font-semibold text-slate-700">Drive {duration(row.minutes)}</span>
        <span>· {miles(row.miles)}</span>
        {row.via && <span className="truncate text-slate-500">· via {row.via}</span>}
      </span>
    </li>
  );
}

function buildRows(plan: TripPlan): Row[] {
  const rows: Row[] = [];
  const stopsByStart = new Map(plan.stops.map((stop) => [stop.arrival, stop]));
  let drive: Extract<Row, { kind: "drive" }> | null = null;
  for (const segment of plan.timeline) {
    if (segment.status === "D") {
      if (!drive) {
        const via = segment.leg !== null ? plan.route.legs[segment.leg]?.summary ?? "" : "";
        drive = { kind: "drive", start: segment.start, end: segment.end, minutes: 0, miles: 0, via, day: segment.start.slice(0, 10) };
        rows.push(drive);
      }
      drive.end = segment.end;
      drive.minutes += segment.minutes;
      drive.miles += segment.miles_end - segment.miles_start;
      continue;
    }
    drive = null;
    const stop = stopsByStart.get(segment.start);
    if (stop) rows.push({ kind: "stop", stop, day: stop.arrival.slice(0, 10) });
  }
  return rows;
}
