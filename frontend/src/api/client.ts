import type { ApiErrorBody, GeoResult, TripPlan, TripRequest } from "./types";

// Same origin on Vercel; set VITE_API_BASE_URL when the API is deployed separately.
const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

export class ApiError extends Error {
  readonly status: number;
  readonly field: string | null;

  constructor(message: string, status: number, field: string | null = null) {
    super(message);
    this.status = status;
    this.field = field;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { Accept: "application/json", ...(init?.body ? { "Content-Type": "application/json" } : {}) },
    });
  } catch (error) {
    if ((error as Error).name === "AbortError") throw error;
    throw new ApiError("Can't reach the trip planner. Check your connection and try again.", 0);
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const err = body as ApiErrorBody | null;
    throw new ApiError(err?.detail ?? `Request failed (HTTP ${response.status}).`, response.status, err?.field ?? null);
  }
  return body as T;
}

export function planTrip(trip: TripRequest, signal?: AbortSignal): Promise<TripPlan> {
  return request<TripPlan>("/api/trips/plan", { method: "POST", body: JSON.stringify(trip), signal });
}

export async function searchPlaces(query: string, signal?: AbortSignal): Promise<GeoResult[]> {
  const params = new URLSearchParams({ q: query, limit: "6" });
  const data = await request<{ results: GeoResult[] }>(`/api/geocode?${params}`, { signal });
  return data.results;
}

export async function reverseGeocode(lat: number, lon: number): Promise<GeoResult> {
  const params = new URLSearchParams({ lat: String(lat), lon: String(lon) });
  const data = await request<{ result: GeoResult }>(`/api/reverse-geocode?${params}`);
  return data.result;
}

/** Wake a cold serverless instance while the user is still typing. */
export function warmUp(): void {
  fetch(`${API_BASE}/api/health`).catch(() => undefined);
}
