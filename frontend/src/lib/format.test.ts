import { describe, expect, it } from "vitest";
import { clock, dayLabel, duration, hhmm, minuteOfDay, nextQuarterHour, nextSixAm } from "./format";

describe("format", () => {
  it("formats ELD-style hours:minutes", () => {
    expect(hhmm(0)).toBe("0:00");
    expect(hhmm(660)).toBe("11:00");
    expect(hhmm(1440)).toBe("24:00");
    expect(hhmm(487)).toBe("8:07");
  });

  it("formats durations, optionally with days", () => {
    expect(duration(45)).toBe("45m");
    expect(duration(600)).toBe("10h");
    expect(duration(1867, { days: true })).toBe("1d 7h 7m");
    expect(duration(0)).toBe("0m");
  });

  it("formats home-terminal wall-clock strings without time-zone conversion", () => {
    expect(clock("2026-10-05T00:05")).toBe("12:05 AM");
    expect(clock("2026-10-05T13:30")).toBe("1:30 PM");
    expect(dayLabel("2026-10-05T06:00")).toBe("Mon, Oct 5");
    expect(minuteOfDay(1110)).toBe("18:30");
  });

  it("rounds the default departure up to the next quarter hour", () => {
    expect(nextQuarterHour(new Date(2026, 9, 5, 8, 1))).toBe("2026-10-05T08:15");
    expect(nextQuarterHour(new Date(2026, 9, 5, 8, 45))).toBe("2026-10-05T08:45");
    expect(nextQuarterHour(new Date(2026, 9, 5, 23, 50))).toBe("2026-10-06T00:00");
  });

  it("starts examples at the next 6:00 AM", () => {
    expect(nextSixAm(new Date(2026, 9, 5, 4, 0))).toBe("2026-10-05T06:00");
    expect(nextSixAm(new Date(2026, 9, 5, 9, 0))).toBe("2026-10-06T06:00");
    expect(nextSixAm(new Date(2026, 9, 31, 22, 0))).toBe("2026-11-01T06:00");
  });
});
