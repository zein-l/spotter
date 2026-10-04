import type { DutyStatus } from "../api/types";

/** 754 -> "12:34" (ELD-style hours:minutes). */
export function hhmm(minutes: number): string {
  const m = Math.max(0, Math.round(minutes));
  return `${Math.floor(m / 60)}:${String(m % 60).padStart(2, "0")}`;
}

/** 754 -> "12h 34m"; 1570 -> "1d 2h 10m" when days are requested. */
export function duration(minutes: number, { days = false } = {}): string {
  const m = Math.max(0, Math.round(minutes));
  const d = days ? Math.floor(m / 1440) : 0;
  const h = Math.floor((m - d * 1440) / 60);
  const min = m % 60;
  const parts = [d ? `${d}d` : "", h ? `${h}h` : "", min || (!d && !h) ? `${min}m` : ""];
  return parts.filter(Boolean).join(" ");
}

export function hours(minutes: number, digits = 1): string {
  return (minutes / 60).toFixed(digits).replace(/\.0+$/, "");
}

export function miles(value: number): string {
  return `${Math.round(value).toLocaleString("en-US")} mi`;
}

// API times are home-terminal wall-clock strings ("2026-10-05T06:30"); format them without
// any time-zone conversion.
function parts(iso: string) {
  const [date, time = "00:00"] = iso.split("T");
  const [y, mo, d] = date.split("-").map(Number);
  const [h, mi] = time.split(":").map(Number);
  return { y, mo, d, h, mi };
}

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function clock(iso: string): string {
  const { h, mi } = parts(iso);
  const suffix = h < 12 ? "AM" : "PM";
  return `${h % 12 || 12}:${String(mi).padStart(2, "0")} ${suffix}`;
}

export function dayLabel(iso: string): string {
  const { y, mo, d } = parts(iso);
  const weekday = WEEKDAYS[new Date(Date.UTC(y, mo - 1, d)).getUTCDay()];
  return `${weekday}, ${MONTHS[mo - 1]} ${d}`;
}

export function dateTime(iso: string): string {
  return `${dayLabel(iso)} · ${clock(iso)}`;
}

export function minuteOfDay(minute: number): string {
  const h = Math.floor(minute / 60) % 24;
  const m = minute % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

export function sameDay(a: string, b: string): boolean {
  return a.slice(0, 10) === b.slice(0, 10);
}

/** Local "YYYY-MM-DDTHH:mm" for <input type="datetime-local">, rounded up to 15 minutes. */
export function nextQuarterHour(now = new Date()): string {
  const d = new Date(now);
  d.setSeconds(0, 0);
  d.setMinutes(Math.ceil(d.getMinutes() / 15) * 15);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export const STATUS_LABEL: Record<DutyStatus, string> = {
  OFF: "Off duty",
  SB: "Sleeper berth",
  D: "Driving",
  ON: "On duty (not driving)",
};

export const STATUS_SHORT: Record<DutyStatus, string> = {
  OFF: "Off",
  SB: "Sleeper",
  D: "Driving",
  ON: "On duty",
};

/** Colours shared by the itinerary, map and charts (log sheets stay black on white). */
export const STATUS_COLOR: Record<DutyStatus, string> = {
  OFF: "#64748b",
  SB: "#6366f1",
  D: "#0d9488",
  ON: "#f59e0b",
};

/** The next 06:00 (today if it's still early, otherwise tomorrow): a typical early start. */
export function nextSixAm(now = new Date()): string {
  const d = new Date(now);
  if (d.getHours() >= 6) d.setDate(d.getDate() + 1);
  d.setHours(6, 0, 0, 0);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T06:00`;
}
