// Mirrors the JSON returned by POST /api/trips/plan (backend/trips/services/trip_planner.py).

export type DutyStatus = "OFF" | "SB" | "D" | "ON";

export type Activity =
  | "off_duty"
  | "pre_trip"
  | "drive"
  | "pickup"
  | "dropoff"
  | "fuel"
  | "break"
  | "rest"
  | "restart"
  | "post_trip";

export type StopType = "start" | "pickup" | "dropoff" | "fuel" | "break" | "rest" | "restart" | "end";
export type Waypoint = "current" | "pickup" | "dropoff";

export interface LocationValue {
  label: string;
  lat?: number | null;
  lon?: number | null;
}

export interface GeoResult {
  label: string;
  lat: number;
  lon: number;
  kind: "city" | "address" | "street" | "place" | "region" | "point";
  source: string;
}

export interface TripOptions {
  pickup_minutes: number;
  dropoff_minutes: number;
  fuel_interval_miles: number;
  fuel_minutes: number;
  pre_trip_minutes: number;
  post_trip_minutes: number;
  rest_in_sleeper: boolean;
}

export interface TripRequest {
  current_location: LocationValue;
  pickup_location: LocationValue;
  dropoff_location: LocationValue;
  current_cycle_used: number;
  departure: string; // "YYYY-MM-DDTHH:mm", home-terminal time
  options: TripOptions;
}

export interface RouteStep {
  instruction: string;
  road: string;
  distance_miles: number;
  duration_minutes: number;
  lat: number;
  lon: number;
  maneuver: string;
}

export interface RouteLeg {
  from: string;
  to: string;
  distance_miles: number;
  drive_minutes: number;
  summary: string;
  geometry: [number, number][]; // [lon, lat]
  steps: RouteStep[];
}

export interface TimelineSegment {
  status: DutyStatus;
  activity: Activity;
  label: string;
  start: string;
  end: string;
  offset_minutes: number;
  minutes: number;
  place: string;
  place_detail: string;
  waypoint: Waypoint | null;
  lat: number;
  lon: number;
  end_lat: number;
  end_lon: number;
  miles_start: number;
  miles_end: number;
  cycle_after_minutes: number;
  leg: number | null;
}

export interface StopActivity {
  activity: Activity;
  label: string;
  status: DutyStatus;
  start: string;
  end: string;
  minutes: number;
}

export interface Stop {
  index: number;
  type: StopType;
  title: string;
  place: string;
  place_detail: string;
  waypoint: Waypoint | null;
  lat: number;
  lon: number;
  arrival: string;
  departure: string;
  minutes: number;
  miles_from_start: number;
  activities: StopActivity[];
}

export interface GridLine {
  status: DutyStatus;
  start: number; // minute of day
  end: number;
}

export interface Remark {
  minute: number;
  status: DutyStatus;
  activity: Activity;
  note: string;
  place: string;
  place_detail: string;
}

export interface DailyLog {
  day: number;
  date: string;
  lines: GridLine[];
  totals: Record<DutyStatus, number>;
  miles: number;
  from: { name: string; detail: string };
  to: { name: string; detail: string };
  remarks: Remark[];
  brackets: { start: number; end: number; place: string }[];
  recap: {
    on_duty_today_minutes: number;
    cycle_total_minutes: number;
    available_tomorrow_minutes: number;
    restart_completed: boolean;
  };
  legs: number[];
}

export interface ComplianceCheck {
  id: string;
  label: string;
  limit: number;
  actual: number;
  unit: "minutes" | "miles" | "gaps";
  passed: boolean;
  detail: string;
}

export interface TripPlan {
  locations: Record<Waypoint, { label: string; lat: number; lon: number; source: string }>;
  route: {
    provider: string;
    profile: string;
    is_estimate: boolean;
    distance_miles: number;
    drive_minutes: number;
    legs: RouteLeg[];
  };
  summary: {
    departure: string;
    pickup_arrival: string;
    dropoff_arrival: string;
    trip_end: string;
    total_minutes: number;
    total_miles: number;
    driving_minutes: number;
    on_duty_minutes: number;
    off_duty_minutes: number;
    sleeper_minutes: number;
    average_speed_mph: number;
    log_days: number;
    fuel_stops: number;
    breaks: number;
    rests: number;
    restarts: number;
    cycle_used_start_minutes: number;
    cycle_used_end_minutes: number;
    cycle_available_end_minutes: number;
  };
  timeline: TimelineSegment[];
  stops: Stop[];
  daily_logs: DailyLog[];
  compliance: { passed: boolean; checks: ComplianceCheck[] };
  assumptions: string[];
  warnings: string[];
}

export interface ApiErrorBody {
  detail: string;
  field: string | null;
  errors: Record<string, unknown> | null;
}

// Header details printed on the log sheet; kept in the browser only.
export interface LogDetails {
  driverName: string;
  coDriver: string;
  carrier: string;
  mainOffice: string;
  homeTerminal: string;
  truckNumber: string;
  trailerNumber: string;
  shippingDoc: string;
  shipper: string;
  commodity: string;
}
