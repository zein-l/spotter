import clsx from "clsx";
import { AlertTriangle, BookOpenCheck, Code2, ListOrdered, Map as MapIcon, NotebookText, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ApiError, planTrip, warmUp } from "./api/client";
import type { LogDetails, TripPlan, TripRequest } from "./api/types";
import TripForm, { type FieldErrors, type FormValues } from "./components/form/TripForm";
import LogSheets from "./components/logs/LogSheets";
import RouteMap from "./components/map/RouteMap";
import Compliance from "./components/results/Compliance";
import Directions from "./components/results/Directions";
import Itinerary from "./components/results/Itinerary";
import SummaryCards from "./components/results/SummaryCards";
import type { ExampleTrip } from "./lib/examples";
import { nextQuarterHour, nextSixAm } from "./lib/format";
import { DEFAULT_OPTIONS, loadLogDetails, saveLogDetails } from "./lib/storage";
import { readTripFromUrl, writeTripToUrl } from "./lib/urlState";

const API_FIELDS: Record<string, keyof FieldErrors> = {
  current_location: "current",
  pickup_location: "pickup",
  dropoff_location: "dropoff",
  current_cycle_used: "cycleUsed",
  departure: "departure",
};
const REPO_URL = "https://github.com/zein-l/spotter";

function emptyForm(): FormValues {
  return {
    current: { label: "" },
    pickup: { label: "" },
    dropoff: { label: "" },
    cycleUsed: "0",
    departure: nextQuarterHour(),
    options: DEFAULT_OPTIONS,
  };
}

function validate(values: FormValues): FieldErrors {
  const errors: FieldErrors = {};
  if (!values.current.label.trim()) errors.current = "Enter where the driver is now.";
  if (!values.pickup.label.trim()) errors.pickup = "Enter the pickup location.";
  if (!values.dropoff.label.trim()) errors.dropoff = "Enter the drop-off location.";
  const cycle = Number(values.cycleUsed);
  if (values.cycleUsed.trim() === "" || !Number.isFinite(cycle) || cycle < 0 || cycle > 70) {
    errors.cycleUsed = "Enter the hours used in the current cycle, 0 to 70.";
  }
  if (!/^\d{4}-\d\d-\d\dT\d\d:\d\d/.test(values.departure)) errors.departure = "Choose a departure date and time.";
  return errors;
}

function toRequest(values: FormValues): TripRequest {
  return {
    current_location: values.current,
    pickup_location: values.pickup,
    dropoff_location: values.dropoff,
    current_cycle_used: Number(values.cycleUsed),
    departure: values.departure.slice(0, 16),
    options: values.options,
  };
}

export default function App() {
  const shared = useMemo(() => readTripFromUrl(), []);
  const [values, setValues] = useState<FormValues>(() =>
    shared ? { ...shared, cycleUsed: String(shared.cycleUsed) } : emptyForm(),
  );
  const [details, setDetails] = useState<LogDetails>(loadLogDetails);
  const [plan, setPlan] = useState<TripPlan | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [selectedStop, setSelectedStop] = useState<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const resultsRef = useRef<HTMLDivElement>(null);

  useEffect(() => warmUp(), []);
  useEffect(() => saveLogDetails(details), [details]);

  const submit = useCallback(async (form: FormValues) => {
    const errors = validate(form);
    setFieldErrors(errors);
    if (Object.keys(errors).length) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    setError(null);
    try {
      const result = await planTrip(toRequest(form), controller.signal);
      const resolved: FormValues = {
        ...form,
        current: { ...result.locations.current },
        pickup: { ...result.locations.pickup },
        dropoff: { ...result.locations.dropoff },
      };
      setPlan(result);
      setSelectedStop(null);
      setValues(resolved);
      writeTripToUrl({ ...resolved, cycleUsed: Number(form.cycleUsed) });
      if (window.matchMedia("(max-width: 1023px)").matches) {
        resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      const field = err instanceof ApiError && err.field ? API_FIELDS[err.field] : undefined;
      if (field) setFieldErrors({ [field]: (err as Error).message.replace(/^[^:]+: /, "") });
      else setError((err as Error).message || "Something went wrong.");
    } finally {
      if (abortRef.current === controller) setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (shared) submit({ ...shared, cycleUsed: String(shared.cycleUsed) });
  }, [shared, submit]);

  const runExample = (example: ExampleTrip) => {
    const next: FormValues = {
      ...values,
      current: example.current,
      pickup: example.pickup,
      dropoff: example.dropoff,
      cycleUsed: String(example.cycleUsed),
      departure: nextSixAm(),
    };
    setValues(next);
    submit(next);
  };

  return (
    <div className="min-h-screen">
      <Header />
      <div className="app-layout mx-auto grid max-w-[1760px] gap-5 px-3 py-4 sm:px-5 lg:grid-cols-[392px_minmax(0,1fr)] lg:py-5">
        <aside className="print-hide lg:sticky lg:top-[84px] lg:max-h-[calc(100vh-100px)] lg:overflow-y-auto lg:pr-1 lg:[scrollbar-width:thin]">
          <div className="card p-4 sm:p-5">
            <h2 className="text-[17px] font-bold text-slate-900">Plan a trip</h2>
            <p className="mt-0.5 mb-4 text-[13px] text-slate-500">
              Property-carrying driver · 70 hours / 8 days · no adverse conditions
            </p>
            <TripForm
              values={values}
              onChange={(v) => {
                setValues(v);
                if (Object.keys(fieldErrors).length) setFieldErrors({});
              }}
              details={details}
              onDetailsChange={setDetails}
              errors={fieldErrors}
              loading={loading}
              onSubmit={() => submit(values)}
              onExample={runExample}
            />
          </div>
        </aside>

        <main ref={resultsRef} className="min-w-0 scroll-mt-20 space-y-5">
          {error && (
            <div role="alert" className="print-hide flex items-start gap-3 rounded-2xl border border-coral-500/30 bg-coral-500/8 px-4 py-3 text-[13.5px] text-coral-600">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" />
              <div>
                <p className="font-semibold">Couldn&apos;t plan this trip</p>
                <p className="text-slate-700">{error}</p>
              </div>
            </div>
          )}
          {plan?.warnings.map((warning) => (
            <div key={warning} className="print-hide flex items-start gap-3 rounded-2xl border border-amber-300/60 bg-amber-50 px-4 py-3 text-[13px] text-amber-900">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" /> {warning}
            </div>
          ))}

          {plan ? (
            <div className={clsx("print-hide transition", loading && "opacity-60")}>
              <SummaryCards plan={plan} onShowCompliance={() => document.getElementById("compliance")?.scrollIntoView({ behavior: "smooth" })} />
            </div>
          ) : (
            <Intro loading={loading} />
          )}

          {plan && <SectionNav />}

          <section id="route" className="card print-hide scroll-mt-28 overflow-hidden">
            <div className={clsx("grid", plan && "xl:grid-cols-[minmax(0,1fr)_380px]")}>
              <div className={clsx("relative", plan ? "h-[420px] sm:h-[520px] xl:h-[600px]" : "h-[380px] sm:h-[460px]")}>
                <RouteMap plan={plan} selectedStop={selectedStop} onSelectStop={setSelectedStop} loading={loading} />
              </div>
              {plan && (
                <div className="flex max-h-[600px] flex-col border-t border-mist-200 xl:border-t-0 xl:border-l">
                  <div className="border-b border-mist-200 px-4 py-3">
                    <h2 className="text-[15px] font-bold text-slate-900">Stops &amp; rests</h2>
                    <p className="text-[12px] text-slate-500">Select a stop to find it on the map.</p>
                  </div>
                  <div className="flex-1 overflow-y-auto px-3 pt-1 pb-3">
                    <Itinerary plan={plan} selectedStop={selectedStop} onSelectStop={setSelectedStop} />
                  </div>
                </div>
              )}
            </div>
          </section>

          {plan && (
            <>
              <Section id="logs" icon={<NotebookText />} title="Driver's daily logs" subtitle="One sheet per calendar day, drawn from the planned duty statuses. Hover the grid line for times.">
                <LogSheets plan={plan} details={details} />
              </Section>
              <Section id="compliance" icon={<ShieldCheck />} title="Hours-of-service audit" subtitle="Every limit re-checked against the finished plan." className="print-hide">
                <div className="card p-4 sm:p-5">
                  <Compliance plan={plan} />
                </div>
              </Section>
              <Section id="directions" icon={<ListOrdered />} title="Route directions" subtitle={`${plan.route.provider} · ${plan.route.profile}`} className="print-hide">
                <div className="card p-3 sm:p-4">
                  <Directions legs={plan.route.legs} />
                </div>
              </Section>
            </>
          )}
        </main>
      </div>
      <Footer />
    </div>
  );
}

function Header() {
  return (
    <header className="print-hide sticky top-0 z-40 border-b border-ink-950/40 bg-ink-900 text-white">
      <div className="mx-auto flex h-16 max-w-[1760px] items-center gap-3 px-3 sm:px-5">
        <img src="/favicon.svg" alt="" className="size-9 rounded-lg ring-1 ring-white/15" />
        <div className="min-w-0">
          <p className="truncate text-[16px] leading-tight font-bold tracking-tight">ELD Trip Planner</p>
          <p className="truncate text-[12px] text-white/65">Routes, required stops &amp; daily logs under FMCSA hours of service</p>
        </div>
        <nav className="ml-auto flex items-center gap-1">
          <a
            href="https://www.fmcsa.dot.gov/regulations/hours-of-service"
            target="_blank"
            rel="noreferrer"
            className="hidden items-center gap-1.5 rounded-lg px-3 py-2 text-[13px] font-medium text-white/80 hover:bg-white/10 hover:text-white md:flex"
          >
            <BookOpenCheck className="size-4" /> HOS rules
          </a>
          <a
            href={REPO_URL}
            target="_blank"
            rel="noreferrer"
            aria-label="Source code on GitHub"
            className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-[13px] font-medium text-white/80 hover:bg-white/10 hover:text-white"
          >
            <Code2 className="size-4" /> <span className="hidden sm:inline">Source</span>
          </a>
        </nav>
      </div>
    </header>
  );
}

function SectionNav() {
  const links = [
    { href: "#route", label: "Map & stops", icon: <MapIcon /> },
    { href: "#logs", label: "Daily logs", icon: <NotebookText /> },
    { href: "#compliance", label: "HOS audit", icon: <ShieldCheck /> },
    { href: "#directions", label: "Directions", icon: <ListOrdered /> },
  ];
  return (
    <nav className="print-hide sticky top-[72px] z-30 -my-1 flex gap-1 overflow-x-auto rounded-2xl border border-mist-200 bg-white/90 p-1 shadow-sm backdrop-blur [scrollbar-width:none]">
      {links.map((link) => (
        <a
          key={link.href}
          href={link.href}
          className="flex shrink-0 items-center gap-1.5 rounded-xl px-3 py-1.5 text-[13px] font-semibold text-slate-600 transition hover:bg-mist-100 hover:text-ink-900 [&_svg]:size-4"
        >
          {link.icon}
          {link.label}
        </a>
      ))}
    </nav>
  );
}

function Section(props: { id: string; icon: ReactNode; title: string; subtitle: string; children: ReactNode; className?: string }) {
  return (
    <section id={props.id} className={clsx("scroll-mt-28", props.className)}>
      <div className="no-print mb-3 flex items-start gap-2.5 px-1">
        <span className="mt-0.5 grid size-8 place-items-center rounded-lg bg-ink-900 text-white [&_svg]:size-4">{props.icon}</span>
        <div>
          <h2 className="text-[17px] font-bold text-slate-900">{props.title}</h2>
          <p className="text-[12.5px] text-slate-500">{props.subtitle}</p>
        </div>
      </div>
      {props.children}
    </section>
  );
}

function Intro({ loading }: { loading: boolean }) {
  const rules = [
    ["11 h", "driving after 10 h off"],
    ["14 h", "on-duty window per shift"],
    ["30 min", "break after 8 h driving"],
    ["70 h", "on duty in 8 days, 34 h restart"],
  ];
  return (
    <div className="card print-hide overflow-hidden">
      <div className="relative bg-gradient-to-br from-ink-900 via-ink-800 to-ink-700 px-5 py-6 text-white sm:px-7">
        <h1 className="text-[22px] font-bold tracking-tight sm:text-[26px]">
          {loading ? "Planning your trip…" : "From trip details to finished daily logs."}
        </h1>
        <p className="mt-1.5 max-w-2xl text-[14px] text-white/75">
          Enter where the driver is, the pickup and drop-off, and the hours already used. The planner routes the truck, schedules every
          legally required break, rest, fuel stop and restart, then fills out a driver&apos;s daily log for each day.
        </p>
        <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
          {rules.map(([value, label]) => (
            <div key={value} className="rounded-xl bg-white/10 px-3 py-2 ring-1 ring-white/15">
              <p className="text-[17px] font-bold">{value}</p>
              <p className="text-[12px] text-white/70">{label}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Footer() {
  return (
    <footer className="print-hide mx-auto max-w-[1760px] px-4 pt-2 pb-8 text-[11.5px] leading-relaxed text-slate-500 sm:px-6">
      Routing by OSRM on OpenStreetMap data · geocoding by Photon (komoot) · map tiles by OpenFreeMap · town names from GeoNames (CC BY
      4.0). Planning aid based on the FMCSA Interstate Truck Driver&apos;s Guide to Hours of Service (2022); not legal advice.
    </footer>
  );
}
