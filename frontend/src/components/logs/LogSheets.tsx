import clsx from "clsx";
import { ChevronDown, Printer } from "lucide-react";
import { useState } from "react";
import type { DailyLog, LogDetails, TripPlan } from "../../api/types";
import { dayLabel, hhmm, minuteOfDay, STATUS_COLOR, STATUS_SHORT } from "../../lib/format";
import LogSheet from "./LogSheet";

interface Props {
  plan: TripPlan;
  details: LogDetails;
}

export default function LogSheets({ plan, details }: Props) {
  const filled = { ...details, shipper: details.shipper || plan.locations.pickup.label };
  return (
    <div className="space-y-5">
      <div className="no-print flex flex-wrap items-center gap-2">
        {plan.daily_logs.map((log) => (
          <a
            key={log.day}
            href={`#log-day-${log.day}`}
            className="rounded-full border border-mist-200 bg-white px-3 py-1 text-[12.5px] font-medium text-slate-700 transition hover:border-ink-700/40 hover:text-ink-900"
          >
            Day {log.day} · {dayLabel(log.date)}
          </a>
        ))}
        <button
          type="button"
          onClick={() => printLogs(null)}
          className="ml-auto inline-flex items-center gap-1.5 rounded-full bg-ink-900 px-3.5 py-1.5 text-[12.5px] font-semibold text-white hover:bg-ink-800"
        >
          <Printer className="size-3.5" /> Print / save all as PDF
        </button>
      </div>
      {plan.daily_logs.map((log) => (
        <SheetCard key={log.day} log={log} details={filled} totalDays={plan.daily_logs.length} />
      ))}
    </div>
  );
}

function SheetCard({ log, details, totalDays }: { log: DailyLog; details: LogDetails; totalDays: number }) {
  const [showRemarks, setShowRemarks] = useState(false);
  return (
    <article id={`log-day-${log.day}`} className="card print-sheet scroll-mt-24 overflow-hidden" data-day={log.day}>
      <header className="no-print flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-mist-200 px-4 py-3">
        <div>
          <p className="text-[11.5px] font-semibold tracking-wide text-slate-500 uppercase">
            Day {log.day} of {totalDays}
          </p>
          <h3 className="text-[15px] font-bold text-slate-900">{dayLabel(log.date)}, {log.date.slice(0, 4)}</h3>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {(["D", "ON", "SB", "OFF"] as const).map((status) => (
            <span key={status} className="inline-flex items-center gap-1.5 rounded-full bg-mist-50 px-2.5 py-1 text-[12px] text-slate-700 ring-1 ring-mist-200">
              <span className="size-2 rounded-full" style={{ background: STATUS_COLOR[status] }} />
              {STATUS_SHORT[status]} <span className="font-semibold tabular-nums">{hhmm(log.totals[status])}</span>
            </span>
          ))}
          <span className="inline-flex items-center rounded-full bg-mist-50 px-2.5 py-1 text-[12px] text-slate-700 ring-1 ring-mist-200">
            <span className="font-semibold tabular-nums">{Math.round(log.miles)}</span>&nbsp;mi
          </span>
        </div>
        <button
          type="button"
          onClick={() => printLogs(log.day)}
          className="ml-auto inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[12.5px] font-semibold text-ink-700 hover:bg-mist-100"
        >
          <Printer className="size-3.5" /> Print day
        </button>
      </header>
      <p className="no-print px-4 pt-2 text-[11.5px] text-slate-500 md:hidden">Swipe sideways to see the full sheet →</p>
      <div className="overflow-x-auto">
        <div className="min-w-[760px] p-2 sm:p-3">
          <LogSheet log={log} details={details} totalDays={totalDays} />
        </div>
      </div>
      <div className="no-print border-t border-mist-200">
        <button
          type="button"
          aria-expanded={showRemarks}
          onClick={() => setShowRemarks((s) => !s)}
          className="flex w-full items-center justify-between px-4 py-2.5 text-[12.5px] font-semibold text-slate-700 hover:bg-mist-50"
        >
          Duty status changes ({log.remarks.length})
          <ChevronDown className={clsx("size-4 transition", showRemarks && "rotate-180")} />
        </button>
        {showRemarks && (
          <div className="overflow-x-auto px-4 pb-3">
            <table className="w-full text-left text-[12.5px]">
              <thead className="text-[11px] tracking-wide text-slate-500 uppercase">
                <tr>
                  <th className="py-1.5 pr-3 font-semibold">Time</th>
                  <th className="py-1.5 pr-3 font-semibold">Status</th>
                  <th className="py-1.5 pr-3 font-semibold">Activity</th>
                  <th className="py-1.5 font-semibold">Location (city, state)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-mist-100">
                {log.remarks.map((remark, i) => (
                  <tr key={i}>
                    <td className="py-1.5 pr-3 font-medium text-slate-900 tabular-nums">{minuteOfDay(remark.minute)}</td>
                    <td className="py-1.5 pr-3 whitespace-nowrap">
                      <span className="inline-flex items-center gap-1.5">
                        <span className="size-2 rounded-full" style={{ background: STATUS_COLOR[remark.status] }} />
                        {STATUS_SHORT[remark.status]}
                      </span>
                    </td>
                    <td className="py-1.5 pr-3 text-slate-700">{remark.note}</td>
                    <td className="py-1.5 text-slate-600">{remark.place_detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </article>
  );
}

function printLogs(day: number | null) {
  const sheets = document.querySelectorAll<HTMLElement>(".print-sheet");
  sheets.forEach((sheet) => sheet.setAttribute("data-print-match", String(day === null || sheet.dataset.day === String(day))));
  if (day !== null) document.body.setAttribute("data-print-day", String(day));
  document.body.setAttribute("data-printing-logs", "true");
  const cleanup = () => {
    document.body.removeAttribute("data-print-day");
    document.body.removeAttribute("data-printing-logs");
    window.removeEventListener("afterprint", cleanup);
  };
  window.addEventListener("afterprint", cleanup);
  window.print();
}
