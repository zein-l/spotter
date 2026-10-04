import { useMemo, useState } from "react";
import type { DailyLog, DutyStatus, LogDetails } from "../../api/types";
import { hhmm, minuteOfDay, STATUS_LABEL } from "../../lib/format";

// Drawing of the FMCSA "Driver's Daily Log" (49 CFR 395.8): header, 24-hour grid with
// 15-minute ticks, the duty-status line, totals, remarks with location brackets, recap.

const W = 1000;
const H = 724;
const GRID_X0 = 128;
const GRID_X1 = 896;
const GRID_TOP = 236;
const ROW_H = 30;
const ROWS: { status: DutyStatus; label: [string, string?] }[] = [
  { status: "OFF", label: ["1. Off Duty"] },
  { status: "SB", label: ["2. Sleeper", "Berth"] },
  { status: "D", label: ["3. Driving"] },
  { status: "ON", label: ["4. On Duty", "(not driving)"] },
];
const GRID_BOTTOM = GRID_TOP + ROW_H * ROWS.length;
const REMARKS_TOP = GRID_BOTTOM + 16;
const RECAP_TOP = 610;
const INK = "#111827";
const MUTED = "#6b7280";
const PEN = "#1d4ed8";
const HOUR_LABELS = ["Mid-\nnight", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "Noon",
  "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "Mid-\nnight"];

const x = (minute: number) => GRID_X0 + ((GRID_X1 - GRID_X0) * minute) / 1440;
const rowIndex = (status: DutyStatus) => ROWS.findIndex((r) => r.status === status);
const rowCenter = (status: DutyStatus) => GRID_TOP + ROW_H * rowIndex(status) + ROW_H / 2;

interface Props {
  log: DailyLog;
  details: LogDetails;
  totalDays: number;
}

export default function LogSheet({ log, details, totalDays }: Props) {
  const [hover, setHover] = useState<number | null>(null);
  const [y, m, d] = log.date.split("-");
  const linePath = useMemo(() => dutyPath(log), [log]);
  const labels = useMemo(() => placeBracketLabels(log), [log]);
  const vehicles = [details.truckNumber && `Truck ${details.truckNumber}`, details.trailerNumber && `Trailer ${details.trailerNumber}`]
    .filter(Boolean)
    .join(" / ");
  const hovered = hover === null ? null : log.lines[hover];

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="h-auto w-full select-none"
      role="img"
      aria-label={`Driver's daily log for ${log.date}: driving ${hhmm(log.totals.D)}, on duty ${hhmm(log.totals.ON)}, sleeper ${hhmm(log.totals.SB)}, off duty ${hhmm(log.totals.OFF)}, ${Math.round(log.miles)} miles.`}
      fontFamily="Inter, ui-sans-serif, system-ui, sans-serif"
    >
      <rect x={0} y={0} width={W} height={H} fill="#fff" />

      {/* ---------------------------------------------------------------- header */}
      <text x={24} y={30} fontSize={8} fill={MUTED} letterSpacing={0.6}>U.S. DEPARTMENT OF TRANSPORTATION</text>
      <text x={24} y={42} fontSize={8} fill={MUTED}>Day {log.day} of {totalDays}</text>
      <text x={W / 2} y={30} fontSize={19} fontWeight={800} textAnchor="middle" fill={INK} letterSpacing={0.5}>DRIVER&apos;S DAILY LOG</text>
      <text x={W / 2} y={44} fontSize={8} textAnchor="middle" fill={MUTED} letterSpacing={0.4}>(ONE CALENDAR DAY — 24 HOURS)</text>
      <text x={W - 24} y={28} fontSize={7.5} textAnchor="end" fill={MUTED}>ORIGINAL — File at home terminal.</text>
      <text x={W - 24} y={39} fontSize={7.5} textAnchor="end" fill={MUTED}>DUPLICATE — Driver retains in his/her possession for 8 days.</text>

      <Field x={24} y={78} w={52} label="(MONTH)" value={m} center />
      <Field x={84} y={78} w={44} label="(DAY)" value={d} center />
      <Field x={136} y={78} w={64} label="(YEAR)" value={y} center />
      <Field x={224} y={78} w={150} label="TOTAL MILES DRIVING TODAY" value={String(Math.round(log.miles))} center />
      <Field x={390} y={78} w={150} label="TOTAL MILEAGE TODAY" value={String(Math.round(log.miles))} center />
      <Field x={564} y={78} w={412} label="TRUCK/TRACTOR AND TRAILER NUMBERS OR LICENSE PLATE(S)/STATE" value={vehicles} center />

      <Field x={24} y={116} w={452} label="FROM" value={log.from.name} inlineLabel="From:" />
      <Field x={500} y={116} w={476} label="TO" value={log.to.name} inlineLabel="To:" />

      <Field x={24} y={154} w={452} label="NAME OF CARRIER OR CARRIERS" value={details.carrier} center />
      <text x={500} y={136} fontSize={7} fill={MUTED}>I certify that these entries are true and correct</text>
      <Field x={500} y={154} w={476} label="DRIVER'S SIGNATURE IN FULL" value={details.driverName} center signature />

      <Field x={24} y={190} w={452} label="MAIN OFFICE ADDRESS" value={details.mainOffice} center />
      <Field x={500} y={190} w={200} label="NAME OF CO-DRIVER" value={details.coDriver || "—"} center />
      <Field x={716} y={190} w={260} label="HOME TERMINAL ADDRESS" value={details.homeTerminal} center />

      {/* ---------------------------------------------------------------- grid */}
      <HourScale y={GRID_TOP - 8} />
      <text x={GRID_X1 + 46} y={GRID_TOP - 14} fontSize={7.5} fontWeight={700} textAnchor="middle" fill={INK}>TOTAL</text>
      <text x={GRID_X1 + 46} y={GRID_TOP - 5} fontSize={7.5} fontWeight={700} textAnchor="middle" fill={INK}>HOURS</text>

      {ROWS.map((row, i) => {
        const top = GRID_TOP + i * ROW_H;
        return (
          <g key={row.status}>
            <rect x={GRID_X0} y={top} width={GRID_X1 - GRID_X0} height={ROW_H} fill={i % 2 ? "#f8fafc" : "#fff"} />
            <text x={24} y={top + (row.label[1] ? 13 : 19)} fontSize={10} fontWeight={600} fill={INK}>{row.label[0]}</text>
            {row.label[1] && <text x={36} y={top + 24} fontSize={8.5} fill={MUTED}>{row.label[1]}</text>}
            {Array.from({ length: 24 * 4 }, (_, q) => {
              if (q % 4 === 0) return null;
              const len = q % 2 === 0 ? ROW_H * 0.45 : ROW_H * 0.25;
              return <line key={q} x1={x(q * 15)} x2={x(q * 15)} y1={top} y2={top + len} stroke={INK} strokeWidth={0.6} />;
            })}
            <text x={GRID_X1 + 46} y={top + 20} fontSize={13} fontWeight={700} fontStyle="italic" textAnchor="middle" fill={PEN}>
              {hhmm(log.totals[row.status])}
            </text>
          </g>
        );
      })}
      {Array.from({ length: 25 }, (_, h) => (
        <line key={h} x1={x(h * 60)} x2={x(h * 60)} y1={GRID_TOP} y2={GRID_BOTTOM} stroke={INK} strokeWidth={h % 12 === 0 ? 1.4 : 0.8} />
      ))}
      {Array.from({ length: ROWS.length + 1 }, (_, i) => (
        <line key={i} x1={GRID_X0} x2={GRID_X1} y1={GRID_TOP + i * ROW_H} y2={GRID_TOP + i * ROW_H} stroke={INK} strokeWidth={i % ROWS.length === 0 ? 1.4 : 0.8} />
      ))}
      <rect x={GRID_X1 + 8} y={GRID_TOP} width={76} height={ROW_H * ROWS.length} fill="none" stroke={INK} strokeWidth={0.8} />
      <line x1={GRID_X1 + 14} x2={GRID_X1 + 78} y1={GRID_BOTTOM + 6} y2={GRID_BOTTOM + 6} stroke={INK} strokeWidth={0.8} />
      <text x={GRID_X1 + 46} y={GRID_BOTTOM + 20} fontSize={13} fontWeight={800} fontStyle="italic" textAnchor="middle" fill={PEN}>
        ={hhmm(Object.values(log.totals).reduce((a, b) => a + b, 0))}
      </text>

      {/* hover highlight + duty line */}
      {hovered && (
        <rect
          x={x(hovered.start)}
          y={GRID_TOP + rowIndex(hovered.status) * ROW_H}
          width={Math.max(2, x(hovered.end) - x(hovered.start))}
          height={ROW_H}
          fill={PEN}
          opacity={0.12}
        />
      )}
      <path d={linePath} fill="none" stroke={PEN} strokeWidth={2.6} strokeLinejoin="miter" strokeLinecap="square" />
      {log.lines.map((line, i) => (
        <rect
          key={i}
          x={x(line.start)}
          y={GRID_TOP + rowIndex(line.status) * ROW_H}
          width={Math.max(4, x(line.end) - x(line.start))}
          height={ROW_H}
          fill="transparent"
          onMouseEnter={() => setHover(i)}
          onMouseLeave={() => setHover(null)}
        >
          <title>{`${minuteOfDay(line.start)}–${line.end === 1440 ? "24:00" : minuteOfDay(line.end)} · ${STATUS_LABEL[line.status]} · ${hhmm(line.end - line.start)}`}</title>
        </rect>
      ))}
      {hovered && <Tooltip line={hovered} />}

      {/* ---------------------------------------------------------------- remarks */}
      <text x={24} y={REMARKS_TOP + 12} fontSize={10} fontWeight={700} fill={INK}>REMARKS</text>
      <line x1={GRID_X0} x2={GRID_X1} y1={REMARKS_TOP} y2={REMARKS_TOP} stroke={INK} strokeWidth={0.8} />
      {Array.from({ length: 24 * 4 + 1 }, (_, q) => (
        <line key={q} x1={x(q * 15)} x2={x(q * 15)} y1={REMARKS_TOP} y2={REMARKS_TOP + (q % 4 === 0 ? 7 : q % 2 === 0 ? 5 : 3)} stroke={INK} strokeWidth={q % 4 === 0 ? 0.8 : 0.5} />
      ))}
      {labels.map((b, i) => {
        const x0 = x(b.start);
        const x1 = x(b.end);
        const cup = REMARKS_TOP + 16;
        return (
          <g key={i}>
            {x1 - x0 >= 3 ? (
              <path d={`M${x0} ${REMARKS_TOP + 8} V${cup} H${x1} V${REMARKS_TOP + 8}`} fill="none" stroke={PEN} strokeWidth={1.6} />
            ) : (
              <line x1={x0} x2={x0} y1={REMARKS_TOP + 8} y2={cup} stroke={PEN} strokeWidth={1.6} />
            )}
            {b.labelX !== b.center && (
              <line x1={b.center} y1={cup} x2={b.labelX} y2={cup + 6} stroke={PEN} strokeWidth={0.7} />
            )}
            <text
              x={b.labelX + 2}
              y={cup + 10}
              fontSize={9.5}
              fontWeight={600}
              fontStyle="italic"
              fill={PEN}
              transform={`rotate(52 ${b.labelX + 2} ${cup + 10})`}
            >
              {b.place}
            </text>
          </g>
        );
      })}

      <text x={24} y={548} fontSize={8} fontWeight={700} fill={INK}>Shipping</text>
      <text x={24} y={558} fontSize={8} fontWeight={700} fill={INK}>Documents:</text>
      <Field x={24} y={584} w={210} label="DVL OR MANIFEST NO." value={details.shippingDoc} />
      <Field x={250} y={584} w={330} label="SHIPPER & COMMODITY" value={[details.shipper, details.commodity].filter(Boolean).join(" — ")} />
      <text x={W - 24} y={572} fontSize={7.5} textAnchor="end" fill={MUTED}>
        Enter name of place you reported and where released from work and when and where each change of duty occurred.
      </text>
      <text x={W - 24} y={583} fontSize={7.5} textAnchor="end" fill={MUTED}>Use time standard of home terminal.</text>

      {/* ---------------------------------------------------------------- recap */}
      <Recap log={log} />
    </svg>
  );
}

function Field(props: {
  x: number;
  y: number;
  w: number;
  label: string;
  value?: string;
  center?: boolean;
  signature?: boolean;
  inlineLabel?: string;
}) {
  const { x: fx, y: fy, w, label, value, center, signature, inlineLabel } = props;
  const valueX = inlineLabel ? fx + 40 : center ? fx + w / 2 : fx + 4;
  return (
    <g>
      {inlineLabel && <text x={fx} y={fy - 4} fontSize={10} fontWeight={700} fill={INK}>{inlineLabel}</text>}
      <line x1={inlineLabel ? fx + 36 : fx} x2={fx + w} y1={fy} y2={fy} stroke={INK} strokeWidth={0.8} />
      {!inlineLabel && (
        <text x={fx + w / 2} y={fy + 9} fontSize={6.5} textAnchor="middle" fill={MUTED} letterSpacing={0.3}>{label}</text>
      )}
      {value && (
        <text
          x={valueX}
          y={fy - 4}
          fontSize={signature ? 15 : 12.5}
          fontWeight={signature ? 600 : 700}
          fontStyle="italic"
          fontFamily={signature ? "'Brush Script MT', 'Segoe Script', cursive" : undefined}
          textAnchor={center && !inlineLabel ? "middle" : "start"}
          fill={PEN}
        >
          {truncate(value, Math.floor(w / (signature ? 8 : 7.2)))}
        </text>
      )}
    </g>
  );
}

function HourScale({ y }: { y: number }) {
  return (
    <g>
      {HOUR_LABELS.map((label, h) => {
        const lines = label.split("\n");
        return (
          <text key={h} x={x(h * 60)} y={y - (lines.length - 1) * 8} fontSize={8} fontWeight={lines.length > 1 ? 700 : 500} textAnchor="middle" fill={INK}>
            {lines.map((part, i) => (
              <tspan key={i} x={x(h * 60)} dy={i ? 8 : 0}>{part}</tspan>
            ))}
          </text>
        );
      })}
    </g>
  );
}

function Tooltip({ line }: { line: { status: DutyStatus; start: number; end: number } }) {
  const text = `${minuteOfDay(line.start)}–${line.end === 1440 ? "24:00" : minuteOfDay(line.end)} · ${STATUS_LABEL[line.status]} · ${hhmm(line.end - line.start)}`;
  const width = text.length * 5.6 + 16;
  const cx = Math.min(Math.max(x((line.start + line.end) / 2), GRID_X0 + width / 2), GRID_X1 - width / 2);
  const top = GRID_TOP + rowIndex(line.status) * ROW_H - 24;
  return (
    <g pointerEvents="none">
      <rect x={cx - width / 2} y={top} width={width} height={18} rx={4} fill={INK} opacity={0.92} />
      <text x={cx} y={top + 12.5} fontSize={9.5} textAnchor="middle" fill="#fff">{text}</text>
    </g>
  );
}

function Recap({ log }: { log: DailyLog }) {
  const cells = [
    { title: "On-duty hours today", sub: "(total of lines 3 & 4)", value: hhmm(log.recap.on_duty_today_minutes) },
    { title: "A. On duty last 8 days", sub: "(including today)", value: hhmm(log.recap.cycle_total_minutes) },
    { title: "B. Available tomorrow", sub: "(70 hours minus A)", value: hhmm(log.recap.available_tomorrow_minutes) },
    {
      title: "34-hour restart",
      sub: log.recap.restart_completed ? "(completed today: 70 h available)" : "(none completed today)",
      value: log.recap.restart_completed ? "Yes" : "No",
    },
  ];
  const left = 24;
  const labelW = 150;
  const cellW = (W - 48 - labelW) / cells.length;
  return (
    <g>
      <rect x={left} y={RECAP_TOP} width={W - 48} height={88} fill="none" stroke={INK} strokeWidth={0.8} />
      <text x={left + 10} y={RECAP_TOP + 22} fontSize={10} fontWeight={700} fill={INK}>Recap:</text>
      <text x={left + 10} y={RECAP_TOP + 35} fontSize={8} fill={MUTED}>Complete at end of day</text>
      <text x={left + 10} y={RECAP_TOP + 58} fontSize={9} fontWeight={700} fill={INK}>70 Hour / 8 Day</text>
      <text x={left + 10} y={RECAP_TOP + 70} fontSize={9} fontWeight={700} fill={INK}>Drivers</text>
      {cells.map((cell, i) => {
        const cx = left + labelW + i * cellW;
        return (
          <g key={cell.title}>
            <line x1={cx} x2={cx} y1={RECAP_TOP} y2={RECAP_TOP + 88} stroke={INK} strokeWidth={0.6} />
            <text x={cx + 10} y={RECAP_TOP + 18} fontSize={8.5} fontWeight={700} fill={INK}>{cell.title}</text>
            <text x={cx + 10} y={RECAP_TOP + 30} fontSize={7.5} fill={MUTED}>{cell.sub}</text>
            <text x={cx + 10} y={RECAP_TOP + 68} fontSize={20} fontWeight={800} fontStyle="italic" fill={PEN}>{cell.value}</text>
          </g>
        );
      })}
    </g>
  );
}

function dutyPath(log: DailyLog): string {
  let d = "";
  log.lines.forEach((line, i) => {
    const yy = rowCenter(line.status);
    d += i === 0 ? `M${x(line.start)} ${yy}` : ` V${yy}`;
    d += ` H${x(line.end)}`;
  });
  return d;
}

/** Brackets under the grid with non-overlapping slanted labels (nudged right when crowded). */
function placeBracketLabels(log: DailyLog) {
  const MIN_GAP = 15;
  let lastX = -Infinity;
  return log.brackets.map((b) => {
    const center = (x(b.start) + x(b.end)) / 2;
    const labelX = Math.max(center, lastX + MIN_GAP);
    lastX = labelX;
    return { ...b, center, labelX };
  });
}

function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, Math.max(1, max - 1))}…` : text;
}
