import clsx from "clsx";
import { LngLatBounds, Map as MapLibre, Marker, NavigationControl, Popup, setWorkerUrl } from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { Stop, TripPlan, Waypoint } from "../../api/types";
import { clock, dayLabel, duration, miles } from "../../lib/format";
import { STOP_STYLE, WAYPOINT_STYLE, type MarkerStyle } from "../../lib/stopStyles";

// MapLibre 6 locates its worker relative to its own module URL, which a bundler rewrites;
// hand it the worker that Vite bundled instead.
setWorkerUrl(workerUrl);

const STYLE_URL = "https://tiles.openfreemap.org/styles/positron";
const FALLBACK_STYLE = {
  version: 8,
  sources: {
    carto: {
      type: "raster",
      tiles: ["a", "b", "c"].map((s) => `https://${s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}@2x.png`),
      tileSize: 256,
      attribution: "© OpenStreetMap contributors © CARTO",
    },
  },
  layers: [
    { id: "background", type: "background", paint: { "background-color": "#eef2f3" } },
    { id: "carto", type: "raster", source: "carto" },
  ],
} as unknown as Parameters<MapLibre["setStyle"]>[0];
const US_VIEW = { center: [-97.5, 39] as [number, number], zoom: 3.2 };
const ROUTE_COLOR = "#0d9488";
const DEADHEAD_COLOR = "#475569";

interface MarkerItem {
  key: string;
  lat: number;
  lon: number;
  style: MarkerStyle;
  waypoint: Waypoint | null;
  title: string;
  stops: Stop[];
}

export interface StopFocus {
  index: number;
  nonce: number; // re-selecting the same stop still re-centres the map
}

interface Props {
  plan: TripPlan | null;
  focus: StopFocus | null;
  onSelectStop: (index: number | null) => void;
  loading?: boolean;
}

export default function RouteMap({ plan, focus, onSelectStop, loading }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibre | null>(null);
  const markersRef = useRef<Map<string, Marker>>(new Map());
  const applyLayersRef = useRef<(() => void) | null>(null);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const [portals, setPortals] = useState<{ item: MarkerItem; pin: HTMLElement; card: HTMLElement }[]>([]);
  const items = useMemo(() => (plan ? markerItems(plan) : []), [plan]);

  // ---------------------------------------------------------------- map lifecycle
  useEffect(() => {
    if (!containerRef.current) return;
    let map: MapLibre;
    try {
      map = new MapLibre({
        container: containerRef.current,
        style: STYLE_URL,
        ...US_VIEW,
        attributionControl: { compact: true },
        dragRotate: false,
        pitchWithRotate: false,
      });
    } catch {
      setFailed(true); // WebGL unavailable
      return;
    }
    mapRef.current = map;
    map.addControl(new NavigationControl({ showCompass: false }), "top-right");
    map.touchZoomRotate.disableRotation();

    let styleLoaded = false;
    let fellBack = false;
    const useFallback = () => {
      if (styleLoaded || fellBack) return;
      fellBack = true;
      map.setStyle(FALLBACK_STYLE, { diff: false });
    };
    // Any error before the first style loads is the style itself failing (tile host down).
    const timer = window.setTimeout(useFallback, 8000);
    map.on("error", () => {
      if (!styleLoaded) useFallback();
    });
    map.on("style.load", () => {
      styleLoaded = true;
      window.clearTimeout(timer);
      setReady(true);
      applyLayersRef.current?.(); // setStyle() (the fallback) wipes custom layers
    });
    const resize = new ResizeObserver(() => map.resize());
    resize.observe(containerRef.current);
    return () => {
      window.clearTimeout(timer);
      resize.disconnect();
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // ---------------------------------------------------------------- route layers
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const data = routeGeoJson(plan);
    const apply = () => {
      const source = map.getSource("route") as { setData?: (d: unknown) => void } | undefined;
      if (source?.setData) {
        source.setData(data);
        return;
      }
      map.addSource("route", { type: "geojson", data });
      const width = ["interpolate", ["linear"], ["zoom"], 3, 3, 8, 5, 12, 7] as unknown as number;
      map.addLayer({
        id: "route-casing",
        type: "line",
        source: "route",
        layout: { "line-join": "round", "line-cap": "round" },
        paint: { "line-color": "#ffffff", "line-width": ["interpolate", ["linear"], ["zoom"], 3, 6, 8, 9, 12, 12] as unknown as number, "line-opacity": 0.95 },
      });
      map.addLayer({
        id: "route-deadhead",
        type: "line",
        source: "route",
        filter: ["==", ["get", "leg"], 0],
        layout: { "line-join": "round", "line-cap": "round" },
        paint: { "line-color": DEADHEAD_COLOR, "line-width": width, "line-dasharray": [1.2, 1.4] },
      });
      map.addLayer({
        id: "route-loaded",
        type: "line",
        source: "route",
        filter: ["==", ["get", "leg"], 1],
        layout: { "line-join": "round", "line-cap": "round" },
        paint: { "line-color": ROUTE_COLOR, "line-width": width },
      });
    };
    applyLayersRef.current = apply;
    apply();
  }, [plan, ready]);

  // ---------------------------------------------------------------- fit to route
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    if (!plan) {
      map.easeTo({ ...US_VIEW, duration: 600 });
      return;
    }
    const bounds = new LngLatBounds();
    plan.route.legs.forEach((leg) => leg.geometry.forEach((c) => bounds.extend(c)));
    Object.values(plan.locations).forEach((l) => bounds.extend([l.lon, l.lat]));
    if (bounds.isEmpty()) return;
    // Leave room for the legend (bottom-left, shown from the sm breakpoint) and the controls.
    const legend = window.matchMedia("(min-width: 640px)").matches;
    const padding = legend ? { top: 76, bottom: 118, left: 64, right: 64 } : { top: 56, bottom: 40, left: 36, right: 36 };
    map.fitBounds(bounds, { padding, maxZoom: 11, duration: 900 });
  }, [plan, ready]);

  // ---------------------------------------------------------------- markers
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const created = items.map((item) => {
      const pin = document.createElement("div");
      const card = document.createElement("div");
      const popup = new Popup({ offset: item.waypoint ? 34 : 18, maxWidth: "300px", focusAfterOpen: false }).setDOMContent(card);
      const marker = new Marker({ element: pin, anchor: item.waypoint ? "bottom" : "center" })
        .setLngLat([item.lon, item.lat])
        .setPopup(popup)
        .addTo(map);
      markersRef.current.set(item.key, marker);
      return { item, pin, card, marker };
    });
    setPortals(created.map(({ item, pin, card }) => ({ item, pin, card })));
    return () => {
      created.forEach(({ item, marker }) => {
        marker.remove();
        markersRef.current.delete(item.key);
      });
    };
  }, [items]);

  // ---------------------------------------------------------------- focus a stop from the itinerary
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !focus || !plan) return;
    const item = items.find((i) => i.stops.some((s) => s.index === focus.index));
    if (!item) return;
    map.flyTo({ center: [item.lon, item.lat], zoom: Math.max(map.getZoom(), 8.5), duration: 900 });
    markersRef.current.forEach((marker, key) => {
      const popup = marker.getPopup();
      if (key === item.key && !popup.isOpen()) marker.togglePopup();
      if (key !== item.key && popup.isOpen()) marker.togglePopup();
    });
  }, [focus, items, plan]);

  const present = useMemo(() => new Set(items.filter((i) => !i.waypoint).map((i) => i.stops[0]?.type)), [items]);

  return (
    <div className="relative h-full min-h-[360px] w-full overflow-hidden bg-[#eef2f3]">
      <div ref={containerRef} className="h-full w-full" />
      {failed && (
        <div className="absolute inset-0 grid place-items-center p-6 text-center text-sm text-slate-500">
          The map needs WebGL, which this browser has disabled. Stops and logs below are unaffected.
        </div>
      )}
      {loading && (
        <div className="absolute inset-0 z-10 grid place-items-center bg-white/45 backdrop-blur-[1px]">
          <div className="flex items-center gap-2 rounded-full bg-white px-4 py-2 text-sm font-medium text-ink-900 shadow-lg">
            <span className="size-2 animate-ping rounded-full bg-ink-700" /> Routing…
          </div>
        </div>
      )}
      {plan?.route.is_estimate && (
        <div className="absolute top-3 left-3 z-10 max-w-[70%] rounded-lg bg-amber-50 px-3 py-2 text-[12px] font-medium text-amber-900 shadow ring-1 ring-amber-200">
          Estimated straight-line route — live routing was unavailable.
        </div>
      )}
      {plan && (
        <div className="pointer-events-none absolute bottom-3 left-3 z-10 hidden rounded-xl bg-white/95 px-3 py-2.5 text-[11.5px] text-slate-600 shadow-md ring-1 ring-mist-200 sm:block">
          <LegendLine color={DEADHEAD_COLOR} dashed label="To pickup" />
          <LegendLine color={ROUTE_COLOR} label="Loaded to drop-off" />
          <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1">
            {(["fuel", "break", "rest", "restart"] as const)
              .filter((t) => present.has(t))
              .map((t) => (
                <span key={t} className="flex items-center gap-1">
                  <span className="size-2.5 rounded-full" style={{ background: STOP_STYLE[t].color }} />
                  {STOP_STYLE[t].label}
                </span>
              ))}
          </div>
        </div>
      )}
      {portals.map(({ item, pin, card }) => (
        <MarkerPortal key={item.key} item={item} pin={pin} card={card} onSelect={onSelectStop} />
      ))}
    </div>
  );
}

function MarkerPortal({ item, pin, card, onSelect }: { item: MarkerItem; pin: HTMLElement; card: HTMLElement; onSelect: (i: number | null) => void }) {
  const Icon = item.style.icon;
  return (
    <>
      {createPortal(
        item.waypoint ? (
          <button
            type="button"
            aria-label={`${item.style.label}: ${item.title}`}
            className="group relative -mb-0.5 flex flex-col items-center"
            onClick={() => onSelect(item.stops[0]?.index ?? null)}
          >
            <span
              className="grid size-9 place-items-center rounded-full text-white shadow-lg ring-[3px] ring-white transition group-hover:scale-105"
              style={{ background: item.style.color }}
            >
              <Icon className="size-[18px]" strokeWidth={2.2} />
            </span>
            <span className="-mt-1 size-2.5 rotate-45 rounded-[2px]" style={{ background: item.style.color }} />
          </button>
        ) : (
          <button
            type="button"
            aria-label={`${item.style.label}: ${item.title}`}
            className="grid size-7 place-items-center rounded-full text-white shadow-md ring-2 ring-white transition hover:scale-110"
            style={{ background: item.style.color }}
            onClick={() => onSelect(item.stops[0]?.index ?? null)}
          >
            <Icon className="size-3.5" strokeWidth={2.4} />
          </button>
        ),
        pin,
      )}
      {createPortal(<StopCard item={item} />, card)}
    </>
  );
}

function StopCard({ item }: { item: MarkerItem }) {
  return (
    <div className="min-w-[210px] text-[12.5px] text-slate-600">
      <p className="text-[11px] font-semibold tracking-wide uppercase" style={{ color: item.style.color }}>
        {item.style.label}
      </p>
      <p className="mt-0.5 text-[14px] font-semibold text-slate-900">{item.title}</p>
      {item.stops.map((stop) => (
        <div key={stop.index} className="mt-2 border-t border-mist-100 pt-2">
          <p className="font-medium text-slate-800">
            {STOP_STYLE[stop.type].label === item.style.label ? "" : `${STOP_STYLE[stop.type].label} · `}
            {dayLabel(stop.arrival)}, {clock(stop.arrival)} – {clock(stop.departure)}
          </p>
          <ul className="mt-1 space-y-0.5">
            {stop.activities.map((a, i) => (
              <li key={i} className="flex justify-between gap-3">
                <span>{a.label}</span>
                <span className="tabular-nums text-slate-500">{duration(a.minutes)}</span>
              </li>
            ))}
          </ul>
          <p className="mt-1 text-[11.5px] text-slate-500">
            {stop.place_detail} · mile {miles(stop.miles_from_start).replace(" mi", "")}
          </p>
        </div>
      ))}
    </div>
  );
}

function LegendLine({ color, label, dashed }: { color: string; label: string; dashed?: boolean }) {
  return (
    <span className="flex items-center gap-2">
      <svg width="26" height="6" aria-hidden>
        <line x1="1" y1="3" x2="25" y2="3" stroke={color} strokeWidth="3.5" strokeLinecap="round" strokeDasharray={dashed ? "4 4" : undefined} />
      </svg>
      <span className={clsx(dashed && "text-slate-500")}>{label}</span>
    </span>
  );
}

function markerItems(plan: TripPlan): MarkerItem[] {
  const items: MarkerItem[] = (["current", "pickup", "dropoff"] as Waypoint[]).map((waypoint) => ({
    key: `wp-${waypoint}`,
    lat: plan.locations[waypoint].lat,
    lon: plan.locations[waypoint].lon,
    style: WAYPOINT_STYLE[waypoint],
    waypoint,
    title: plan.locations[waypoint].label,
    stops: plan.stops.filter((s) => s.waypoint === waypoint),
  }));
  for (const stop of plan.stops) {
    if (stop.waypoint) continue;
    items.push({
      key: `stop-${stop.index}`,
      lat: stop.lat,
      lon: stop.lon,
      style: STOP_STYLE[stop.type],
      waypoint: null,
      title: stop.place_detail,
      stops: [stop],
    });
  }
  // When current location == pickup, show a single pin.
  const current = items[0];
  const pickup = items[1];
  if (Math.abs(current.lat - pickup.lat) < 1e-4 && Math.abs(current.lon - pickup.lon) < 1e-4) {
    pickup.stops = [...current.stops, ...pickup.stops];
    items.splice(0, 1);
  }
  return items;
}

function routeGeoJson(plan: TripPlan | null) {
  return {
    type: "FeatureCollection" as const,
    features: (plan?.route.legs ?? [])
      .map((leg, index) => ({
        type: "Feature" as const,
        properties: { leg: index },
        geometry: { type: "LineString" as const, coordinates: leg.geometry },
      }))
      .filter((f) => f.geometry.coordinates.length > 1),
  };
}
