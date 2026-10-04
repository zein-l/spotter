import clsx from "clsx";
import { Building2, CircleCheck, Loader2, MapPin, Navigation } from "lucide-react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { searchPlaces } from "../../api/client";
import type { GeoResult, LocationValue } from "../../api/types";

interface Props {
  label: string;
  hint?: string;
  icon: ReactNode;
  value: LocationValue;
  onChange: (value: LocationValue) => void;
  placeholder: string;
  error?: string | null;
  action?: ReactNode;
}

const KIND_ICON = {
  city: MapPin,
  address: Building2,
  street: Navigation,
  place: MapPin,
  region: MapPin,
  point: MapPin,
} as const;

export default function LocationInput({ label, hint, icon, value, onChange, placeholder, error, action }: Props) {
  const id = useId();
  const listId = `${id}-list`;
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<GeoResult[]>([]);
  const [active, setActive] = useState(0);
  const typed = useRef(false);
  const resolved = value.lat != null && value.lon != null;

  useEffect(() => {
    const query = value.label.trim();
    if (!typed.current || resolved || query.length < 2) {
      setResults([]);
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    const timer = window.setTimeout(() => {
      searchPlaces(query, controller.signal)
        .then((found) => {
          setResults(found);
          setActive(0);
          setOpen(true);
        })
        .catch((err: Error) => {
          if (err.name !== "AbortError") setResults([]);
        })
        .finally(() => setLoading(false));
    }, 220);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [value.label, resolved]);

  function choose(result: GeoResult) {
    typed.current = false;
    onChange({ label: result.label, lat: result.lat, lon: result.lon });
    setOpen(false);
    setResults([]);
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (!open || results.length === 0) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((i) => (i + 1) % results.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((i) => (i - 1 + results.length) % results.length);
    } else if (event.key === "Enter") {
      event.preventDefault();
      choose(results[active]);
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  }

  const showList = open && results.length > 0;
  return (
    <div className="relative">
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <label htmlFor={id} className="text-[13px] font-semibold text-slate-700">
          {label}
        </label>
        {action}
      </div>
      <div className="relative">
        <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-slate-400">{icon}</span>
        <input
          id={id}
          type="text"
          role="combobox"
          aria-expanded={showList}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={showList ? `${listId}-${active}` : undefined}
          aria-invalid={Boolean(error)}
          aria-describedby={error ? `${id}-error` : undefined}
          autoComplete="off"
          spellCheck={false}
          className={clsx("input pr-9 pl-10", error && "input-error")}
          placeholder={placeholder}
          value={value.label}
          onChange={(event) => {
            typed.current = true;
            onChange({ label: event.target.value, lat: null, lon: null });
          }}
          onFocus={() => results.length && setOpen(true)}
          onBlur={() => setOpen(false)}
          onKeyDown={onKeyDown}
        />
        <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center">
          {loading ? (
            <Loader2 className="size-4 animate-spin text-slate-400" aria-hidden />
          ) : resolved ? (
            <CircleCheck className="size-4 text-emerald-600" aria-label="Location confirmed" />
          ) : null}
        </span>
      </div>
      {showList && (
        <ul
          id={listId}
          role="listbox"
          className="absolute z-30 mt-1.5 max-h-72 w-full overflow-auto rounded-xl border border-mist-200 bg-white p-1 shadow-xl"
        >
          {results.map((result, i) => {
            const Icon = KIND_ICON[result.kind] ?? MapPin;
            return (
              <li
                key={`${result.label}-${i}`}
                id={`${listId}-${i}`}
                role="option"
                aria-selected={i === active}
                onMouseDown={(event) => event.preventDefault()}
                onMouseEnter={() => setActive(i)}
                onClick={() => choose(result)}
                className={clsx(
                  "flex cursor-pointer items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm",
                  i === active ? "bg-mist-100 text-ink-900" : "text-slate-700",
                )}
              >
                <Icon className="size-4 shrink-0 text-slate-400" aria-hidden />
                <span className="truncate">{result.label}</span>
              </li>
            );
          })}
        </ul>
      )}
      {error ? (
        <p id={`${id}-error`} className="mt-1.5 text-[12.5px] font-medium text-coral-600">
          {error}
        </p>
      ) : (
        hint && <p className="mt-1.5 text-[12px] text-slate-500">{hint}</p>
      )}
    </div>
  );
}
