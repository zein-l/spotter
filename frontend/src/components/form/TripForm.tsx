import clsx from "clsx";
import { ChevronDown, Clock3, Crosshair, Flag, Loader2, Package, Route, Truck } from "lucide-react";
import { useState, type ReactNode } from "react";
import { reverseGeocode } from "../../api/client";
import type { LocationValue, LogDetails, TripOptions } from "../../api/types";
import { EXAMPLES, type ExampleTrip } from "../../lib/examples";
import { DEFAULT_OPTIONS } from "../../lib/storage";
import CycleInput from "./CycleInput";
import LocationInput from "./LocationInput";

export interface FormValues {
  current: LocationValue;
  pickup: LocationValue;
  dropoff: LocationValue;
  cycleUsed: string;
  departure: string;
  options: TripOptions;
}

export type FieldErrors = Partial<Record<"current" | "pickup" | "dropoff" | "cycleUsed" | "departure", string>>;

interface Props {
  values: FormValues;
  onChange: (values: FormValues) => void;
  details: LogDetails;
  onDetailsChange: (details: LogDetails) => void;
  errors: FieldErrors;
  loading: boolean;
  onSubmit: () => void;
  onExample: (example: ExampleTrip) => void;
}

export default function TripForm({ values, onChange, details, onDetailsChange, errors, loading, onSubmit, onExample }: Props) {
  const set = <K extends keyof FormValues>(key: K, value: FormValues[K]) => onChange({ ...values, [key]: value });
  const setOption = <K extends keyof TripOptions>(key: K, value: TripOptions[K]) =>
    onChange({ ...values, options: { ...values.options, [key]: value } });
  const optionsChanged = (Object.keys(DEFAULT_OPTIONS) as (keyof TripOptions)[]).some(
    (key) => values.options[key] !== DEFAULT_OPTIONS[key],
  );

  return (
    <form
      className="space-y-5"
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <div className="relative space-y-4">
        <span aria-hidden className="absolute top-[40px] bottom-[42px] left-[19px] w-px border-l-2 border-dotted border-mist-200" />
        <LocationInput
          label="Current location"
          icon={<Truck className="size-4" />}
          value={values.current}
          onChange={(v) => set("current", v)}
          placeholder="Where the driver is now"
          error={errors.current}
          action={<UseMyLocation onLocate={(v) => set("current", v)} />}
        />
        <LocationInput
          label="Pickup location"
          icon={<Package className="size-4" />}
          value={values.pickup}
          onChange={(v) => set("pickup", v)}
          placeholder="Shipper, city or address"
          error={errors.pickup}
        />
        <LocationInput
          label="Drop-off location"
          icon={<Flag className="size-4" />}
          value={values.dropoff}
          onChange={(v) => set("dropoff", v)}
          placeholder="Receiver, city or address"
          error={errors.dropoff}
        />
      </div>

      <CycleInput value={values.cycleUsed} onChange={(v) => set("cycleUsed", v)} error={errors.cycleUsed} />

      <div>
        <label htmlFor="departure" className="field-label">
          Departure <span className="font-normal text-slate-500">(home-terminal time)</span>
        </label>
        <div className="relative">
          <Clock3 className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-slate-400" />
          <input
            id="departure"
            type="datetime-local"
            step={900}
            value={values.departure}
            onChange={(event) => set("departure", event.target.value)}
            className={clsx("input pl-10 tabular-nums", errors.departure && "input-error")}
          />
        </div>
        {errors.departure && <p className="mt-1.5 text-[12.5px] font-medium text-coral-600">{errors.departure}</p>}
      </div>

      <Disclosure title="Trip assumptions" badge={optionsChanged ? "Edited" : "FMCSA defaults"}>
        <div className="grid grid-cols-2 gap-3">
          <NumberField label="Pickup" suffix="min" value={values.options.pickup_minutes} min={0} max={720} onChange={(v) => setOption("pickup_minutes", v)} />
          <NumberField label="Drop-off" suffix="min" value={values.options.dropoff_minutes} min={0} max={720} onChange={(v) => setOption("dropoff_minutes", v)} />
          <NumberField label="Fuel every" suffix="mi" value={values.options.fuel_interval_miles} min={100} max={3000} step={50} onChange={(v) => setOption("fuel_interval_miles", v)} />
          <NumberField label="Fuel stop" suffix="min" value={values.options.fuel_minutes} min={5} max={120} onChange={(v) => setOption("fuel_minutes", v)} />
          <NumberField label="Pre-trip inspection" suffix="min" value={values.options.pre_trip_minutes} min={0} max={120} onChange={(v) => setOption("pre_trip_minutes", v)} />
          <NumberField label="Post-trip inspection" suffix="min" value={values.options.post_trip_minutes} min={0} max={120} onChange={(v) => setOption("post_trip_minutes", v)} />
        </div>
        <label className="mt-3 flex cursor-pointer items-center gap-2.5 text-[13px] text-slate-700">
          <input
            type="checkbox"
            checked={values.options.rest_in_sleeper}
            onChange={(event) => setOption("rest_in_sleeper", event.target.checked)}
            className="size-4 rounded accent-ink-800"
          />
          Log 10-hour rests in the sleeper berth
        </label>
        <button
          type="button"
          onClick={() => onChange({ ...values, options: DEFAULT_OPTIONS })}
          className="mt-3 text-[12.5px] font-semibold text-ink-700 hover:underline disabled:opacity-40"
          disabled={!optionsChanged}
        >
          Reset to assessment defaults
        </button>
      </Disclosure>

      <Disclosure title="Log sheet details" badge="Printed on each sheet">
        <div className="grid grid-cols-2 gap-3">
          <TextField label="Driver" value={details.driverName} onChange={(v) => onDetailsChange({ ...details, driverName: v })} />
          <TextField label="Co-driver" value={details.coDriver} onChange={(v) => onDetailsChange({ ...details, coDriver: v })} />
          <TextField className="col-span-2" label="Carrier" value={details.carrier} onChange={(v) => onDetailsChange({ ...details, carrier: v })} />
          <TextField label="Main office" value={details.mainOffice} onChange={(v) => onDetailsChange({ ...details, mainOffice: v })} />
          <TextField label="Home terminal" value={details.homeTerminal} onChange={(v) => onDetailsChange({ ...details, homeTerminal: v })} />
          <TextField label="Truck / tractor #" value={details.truckNumber} onChange={(v) => onDetailsChange({ ...details, truckNumber: v })} />
          <TextField label="Trailer #" value={details.trailerNumber} onChange={(v) => onDetailsChange({ ...details, trailerNumber: v })} />
          <TextField label="Shipping doc / manifest #" value={details.shippingDoc} onChange={(v) => onDetailsChange({ ...details, shippingDoc: v })} />
          <TextField label="Commodity" value={details.commodity} onChange={(v) => onDetailsChange({ ...details, commodity: v })} />
          <TextField
            className="col-span-2"
            label="Shipper"
            placeholder="Defaults to the pickup location"
            value={details.shipper}
            onChange={(v) => onDetailsChange({ ...details, shipper: v })}
          />
        </div>
      </Disclosure>

      <button
        type="submit"
        disabled={loading}
        className="flex w-full items-center justify-center gap-2 rounded-xl bg-ink-900 px-4 py-3 text-[15px] font-semibold text-white shadow-[0_8px_20px_-8px_rgba(11,58,68,0.6)] transition hover:bg-ink-800 active:translate-y-px disabled:cursor-wait disabled:opacity-80"
      >
        {loading ? <Loader2 className="size-4 animate-spin" /> : <Route className="size-4" />}
        {loading ? "Planning trip…" : "Plan trip & draw logs"}
      </button>

      <div>
        <p className="mb-2 text-[12px] font-semibold tracking-wide text-slate-500 uppercase">Try an example</p>
        <div className="grid gap-2">
          {EXAMPLES.map((example) => (
            <button
              key={example.id}
              type="button"
              disabled={loading}
              onClick={() => onExample(example)}
              className="group rounded-xl border border-mist-200 bg-white px-3 py-2.5 text-left transition hover:border-ink-700/40 hover:bg-mist-50 disabled:opacity-60"
            >
              <span className="block text-[13.5px] font-semibold text-slate-800 group-hover:text-ink-900">{example.title}</span>
              <span className="block text-[12px] text-slate-500">
                {example.blurb} · {example.cycleUsed} h used
              </span>
            </button>
          ))}
        </div>
      </div>
    </form>
  );
}

function UseMyLocation({ onLocate }: { onLocate: (value: LocationValue) => void }) {
  const [state, setState] = useState<"idle" | "busy" | "error">("idle");
  if (!("geolocation" in navigator)) return null;
  return (
    <button
      type="button"
      className="inline-flex items-center gap-1 text-[12px] font-semibold text-ink-700 hover:underline disabled:opacity-60"
      disabled={state === "busy"}
      onClick={() => {
        setState("busy");
        navigator.geolocation.getCurrentPosition(
          async ({ coords }) => {
            try {
              const place = await reverseGeocode(coords.latitude, coords.longitude);
              onLocate({ label: place.label, lat: coords.latitude, lon: coords.longitude });
              setState("idle");
            } catch {
              onLocate({ label: `${coords.latitude.toFixed(4)}, ${coords.longitude.toFixed(4)}`, lat: coords.latitude, lon: coords.longitude });
              setState("idle");
            }
          },
          () => setState("error"),
          { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 },
        );
      }}
    >
      {state === "busy" ? <Loader2 className="size-3.5 animate-spin" /> : <Crosshair className="size-3.5" />}
      {state === "error" ? "Location blocked" : "Use my location"}
    </button>
  );
}

function Disclosure({ title, badge, children }: { title: string; badge?: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-xl border border-mist-200 bg-mist-50/60">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between gap-2 px-3.5 py-3 text-left"
      >
        <span className="text-[13.5px] font-semibold text-slate-800">{title}</span>
        <span className="flex items-center gap-2">
          {badge && <span className="rounded-full bg-white px-2 py-0.5 text-[11px] font-medium text-slate-500 ring-1 ring-mist-200">{badge}</span>}
          <ChevronDown className={clsx("size-4 text-slate-500 transition", open && "rotate-180")} />
        </span>
      </button>
      {open && <div className="border-t border-mist-200 px-3.5 pt-3 pb-3.5">{children}</div>}
    </div>
  );
}

function NumberField(props: { label: string; suffix: string; value: number; min: number; max: number; step?: number; onChange: (v: number) => void }) {
  const { label, suffix, value, min, max, step = 5, onChange } = props;
  return (
    <label className="block">
      <span className="mb-1 block text-[12px] font-medium text-slate-600">{label}</span>
      <span className="relative block">
        <input
          type="number"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(event) => {
            const next = Number(event.target.value);
            if (Number.isFinite(next)) onChange(Math.min(max, Math.max(min, next)));
          }}
          className="input py-2 pr-11 text-sm tabular-nums"
        />
        <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-[12px] text-slate-400">{suffix}</span>
      </span>
    </label>
  );
}

function TextField(props: { label: string; value: string; onChange: (v: string) => void; placeholder?: string; className?: string }) {
  return (
    <label className={clsx("block", props.className)}>
      <span className="mb-1 block text-[12px] font-medium text-slate-600">{props.label}</span>
      <input
        type="text"
        value={props.value}
        placeholder={props.placeholder}
        maxLength={80}
        onChange={(event) => props.onChange(event.target.value)}
        className="input py-2 text-sm"
      />
    </label>
  );
}
