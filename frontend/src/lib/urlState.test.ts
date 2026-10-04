import { describe, expect, it } from "vitest";
import { DEFAULT_OPTIONS } from "./storage";
import { decodeTrip, encodeTrip, type TripInputs } from "./urlState";

const trip: TripInputs = {
  current: { label: "Chicago, IL", lat: 41.8781, lon: -87.6298 },
  pickup: { label: "St. Louis, MO", lat: 38.627, lon: -90.1994 },
  dropoff: { label: "1200 Main St, Dallas, TX" },
  cycleUsed: 12.5,
  departure: "2026-10-05T06:00",
  options: { ...DEFAULT_OPTIONS, fuel_interval_miles: 800, rest_in_sleeper: false },
};

describe("shareable trip URLs", () => {
  it("round-trips inputs, coordinates and non-default options", () => {
    expect(decodeTrip(encodeTrip(trip))).toEqual(trip);
  });

  it("only writes options that differ from the defaults", () => {
    const query = encodeTrip({ ...trip, options: DEFAULT_OPTIONS });
    expect(query).not.toContain("fi=");
    expect(decodeTrip(query)?.options).toEqual(DEFAULT_OPTIONS);
  });

  it("rejects incomplete or malformed links", () => {
    expect(decodeTrip("")).toBeNull();
    expect(decodeTrip("from=Chicago&pickup=StL&to=Dallas&cycle=12&depart=tomorrow")).toBeNull();
  });

  it("clamps the cycle to 0-70 hours", () => {
    const query = encodeTrip(trip).replace("cycle=12.5", "cycle=99");
    expect(decodeTrip(query)?.cycleUsed).toBe(70);
  });
});
