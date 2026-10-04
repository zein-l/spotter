import type { LogDetails, TripOptions } from "../api/types";

export const DEFAULT_OPTIONS: TripOptions = {
  pickup_minutes: 60,
  dropoff_minutes: 60,
  fuel_interval_miles: 1000,
  fuel_minutes: 30,
  pre_trip_minutes: 30,
  post_trip_minutes: 15,
  rest_in_sleeper: true,
};

// Placeholder header values, borrowed from the sample log in the FMCSA driver's guide.
export const DEFAULT_LOG_DETAILS: LogDetails = {
  driverName: "John E. Doe",
  coDriver: "",
  carrier: "John Doe's Transportation",
  mainOffice: "Washington, D.C.",
  homeTerminal: "Washington, D.C.",
  truckNumber: "123",
  trailerNumber: "20544",
  shippingDoc: "101601",
  shipper: "",
  commodity: "General freight",
};

const LOG_DETAILS_KEY = "eld-trip-planner.log-details.v1";

export function loadLogDetails(): LogDetails {
  try {
    const raw = window.localStorage.getItem(LOG_DETAILS_KEY);
    return raw ? { ...DEFAULT_LOG_DETAILS, ...JSON.parse(raw) } : DEFAULT_LOG_DETAILS;
  } catch {
    return DEFAULT_LOG_DETAILS;
  }
}

export function saveLogDetails(details: LogDetails): void {
  try {
    window.localStorage.setItem(LOG_DETAILS_KEY, JSON.stringify(details));
  } catch {
    // Private mode or storage disabled: the details still apply for this visit.
  }
}
