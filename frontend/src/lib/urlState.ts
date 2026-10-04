import type { LocationValue, TripOptions } from "../api/types";
import { DEFAULT_OPTIONS } from "./storage";

// Shareable plans: the inputs live in the query string, e.g.
// ?from=Chicago,%20IL@41.8781,-87.6298&pickup=...&to=...&cycle=12&depart=2026-10-05T06:00

export interface TripInputs {
  current: LocationValue;
  pickup: LocationValue;
  dropoff: LocationValue;
  cycleUsed: number;
  departure: string;
  options: TripOptions;
}

const OPTION_KEYS: Record<keyof TripOptions, string> = {
  pickup_minutes: "pu",
  dropoff_minutes: "do",
  fuel_interval_miles: "fi",
  fuel_minutes: "fm",
  pre_trip_minutes: "pre",
  post_trip_minutes: "post",
  rest_in_sleeper: "sb",
};

function encodeLocation(location: LocationValue): string {
  const hasPoint = location.lat != null && location.lon != null;
  return hasPoint ? `${location.label}@${location.lat!.toFixed(5)},${location.lon!.toFixed(5)}` : location.label;
}

function decodeLocation(raw: string | null): LocationValue | null {
  if (!raw) return null;
  const at = raw.lastIndexOf("@");
  if (at > 0) {
    const [lat, lon] = raw.slice(at + 1).split(",").map(Number);
    if (Number.isFinite(lat) && Number.isFinite(lon)) return { label: raw.slice(0, at), lat, lon };
  }
  return { label: raw };
}

export function writeTripToUrl(inputs: TripInputs): void {
  const params = new URLSearchParams();
  params.set("from", encodeLocation(inputs.current));
  params.set("pickup", encodeLocation(inputs.pickup));
  params.set("to", encodeLocation(inputs.dropoff));
  params.set("cycle", String(inputs.cycleUsed));
  params.set("depart", inputs.departure);
  for (const [key, short] of Object.entries(OPTION_KEYS) as [keyof TripOptions, string][]) {
    if (inputs.options[key] !== DEFAULT_OPTIONS[key]) params.set(short, String(inputs.options[key]));
  }
  window.history.replaceState(null, "", `${window.location.pathname}?${params}`);
}

export function readTripFromUrl(): TripInputs | null {
  const params = new URLSearchParams(window.location.search);
  const current = decodeLocation(params.get("from"));
  const pickup = decodeLocation(params.get("pickup"));
  const dropoff = decodeLocation(params.get("to"));
  const cycle = Number(params.get("cycle"));
  const departure = params.get("depart") ?? "";
  if (!current || !pickup || !dropoff || !Number.isFinite(cycle) || !/^\d{4}-\d\d-\d\dT\d\d:\d\d$/.test(departure)) {
    return null;
  }
  const options = { ...DEFAULT_OPTIONS };
  for (const [key, short] of Object.entries(OPTION_KEYS) as [keyof TripOptions, string][]) {
    const value = params.get(short);
    if (value === null) continue;
    if (key === "rest_in_sleeper") options.rest_in_sleeper = value === "true";
    else if (Number.isFinite(Number(value))) options[key] = Number(value);
  }
  return { current, pickup, dropoff, cycleUsed: Math.min(70, Math.max(0, cycle)), departure, options };
}
