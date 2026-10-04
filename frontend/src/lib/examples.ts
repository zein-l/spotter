import type { LocationValue } from "../api/types";

export interface ExampleTrip {
  id: string;
  title: string;
  blurb: string;
  current: LocationValue;
  pickup: LocationValue;
  dropoff: LocationValue;
  cycleUsed: number;
}

// Coordinates included so the examples never depend on the geocoder.
export const EXAMPLES: ExampleTrip[] = [
  {
    id: "midwest",
    title: "Chicago → St. Louis → Dallas",
    blurb: "2 days · overnight sleeper-berth rest",
    current: { label: "Chicago, IL", lat: 41.8781, lon: -87.6298 },
    pickup: { label: "St. Louis, MO", lat: 38.627, lon: -90.1994 },
    dropoff: { label: "Dallas, TX", lat: 32.7767, lon: -96.797 },
    cycleUsed: 12,
  },
  {
    id: "regional",
    title: "Atlanta → Macon → Jacksonville",
    blurb: "Single day · one log sheet",
    current: { label: "Atlanta, GA", lat: 33.749, lon: -84.388 },
    pickup: { label: "Macon, GA", lat: 32.8407, lon: -83.6324 },
    dropoff: { label: "Jacksonville, FL", lat: 30.3322, lon: -81.6557 },
    cycleUsed: 20,
  },
  {
    id: "coast",
    title: "New York → Columbus → Los Angeles",
    blurb: "Cross-country · fuel stops & a 34-hour restart",
    current: { label: "New York, NY", lat: 40.7128, lon: -74.006 },
    pickup: { label: "Columbus, OH", lat: 39.9612, lon: -82.9988 },
    dropoff: { label: "Los Angeles, CA", lat: 34.0522, lon: -118.2437 },
    cycleUsed: 30,
  },
  {
    id: "cycle",
    title: "Denver → Salt Lake City → Sacramento",
    blurb: "64 cycle hours used · restart planned early",
    current: { label: "Denver, CO", lat: 39.7392, lon: -104.9903 },
    pickup: { label: "Salt Lake City, UT", lat: 40.7608, lon: -111.891 },
    dropoff: { label: "Sacramento, CA", lat: 38.5816, lon: -121.4944 },
    cycleUsed: 64,
  },
];
