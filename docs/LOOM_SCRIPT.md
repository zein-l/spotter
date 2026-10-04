# Loom walkthrough (target: 4 minutes)

Before recording, open the deployed app in one tab and `README.md` in your editor in another.
Plan the Chicago example once so the API is warm. Read the outline below, then say it in your
own words rather than reading it out.

---

## 0:00 – 0:20 · What it is

> "This is an ELD trip planner for a property-carrying driver on the 70-hour/8-day rules. I give
> it the current location, pickup, drop-off and cycle hours used. It returns the route, every
> stop the regulations require, and a filled-out driver's daily log for each day. It's Django
> and DRF on the back end, React and TypeScript on the front, deployed on Vercel."

## 0:20 – 1:30 · Demo: a two-day trip

1. Click **Chicago → St. Louis → Dallas** (12 h used).
2. **Summary cards**: distance, driving time, trip time, two log sheets, cycle 12 h → ~33 h,
   compliant.
3. **Map**: the dashed leg is the empty drive to the pickup; the solid leg is loaded. Click the
   purple pin to show the 10-hour rest.
4. **Stops list**: depart with a pre-trip inspection; the pickup's hour of loading counts as the
   30-minute break, so no separate break is needed; after 11 hours of driving comes the post-trip,
   then 10 hours in the sleeper berth, then the pre-trip.
5. **Daily logs**: scroll to Day 1. Point at the four lines, the totals summing to `=24:00`,
   the remarks with the city and state at each stop (as in the FMCSA example), and the recap at
   the bottom. Hover the line to show the time tooltip. Click **Print / save all as PDF**.

## 1:30 – 2:00 · Demo: the hard case

1. Click **New York → Columbus → Los Angeles** (30 h used): about a week of sheets, fuel stops before every
   1,000 miles, and a 34-hour restart once the 70-hour cycle runs out. On the restart day the
   sheet is all off duty and the recap shows the hours coming back.
2. Scroll to the **HOS audit**: "Every limit is re-checked against the finished plan by separate
   code, so a planner bug would show up here as a failure."

## 2:00 – 3:30 · Code: the HOS engine (open `backend/trips/hos/`)

- `models.py`: the four duty statuses and the rule constants (11, 14, 8/30 min, 70, 10, 34),
  each tagged with its 49 CFR 395 section. All time is integer minutes, so 11:00 is exact.
- `planner.py`: an event-driven simulation over a task list (pre-trip → drive → pickup → drive
  → drop-off). `_drive_step` computes the driving time left before each limit, stops for the
  first one that would be broken, and otherwise drives. Highlight two decisions:
  - **Restart choice**: when the cycle won't last the trip, it simulates both "10-hour rest" and
    "34-hour restart now" and keeps whichever delivers first.
  - **Fuel during a break**: fueling is on-duty, not driving, so it also satisfies the 30-minute
    break.
- `validator.py`: an independent audit of the final timeline.
- `daily_logs.py`: splits the trip at midnight into sheets with totals, remarks and the recap.
  Drives are split at midnight inside the planner, so daily mileage is exact.
- `tests/test_hos.py`: show `test_random_trips_are_always_compliant`, which runs 400 random trips
  through the validator, and `test_restart_choice_is_never_slower_than_greedy`.

## 3:30 – 4:15 · Code: services and frontend

- `services/routing.py`: OSRM with a 65 mph truck cap per step, a mirror fallback, then a
  flagged estimate, so a map outage degrades the plan instead of failing it.
- `services/places.py`: an offline index of 33k towns, so remarks read
  "I-44, 10 mi S of Doolittle, MO" without hammering a reverse geocoder.
- `frontend/src/components/logs/LogSheet.tsx`: the log is SVG drawn from the API's grid lines,
  laid out like the FMCSA paper form, so it's crisp when printed.
- `RouteMap.tsx`: MapLibre with free OpenFreeMap tiles; markers are React portals.

## 4:15 – 4:30 · Wrap up

> "Assumptions are listed in the app and the README. For example, the driver starts rested, and
> prior cycle hours conservatively stay in the 8-day window. Next steps would be split-sleeper
> optimization and snapping stops to real truck stops. Thanks for watching."

---

**Questions you may get, and short answers**

- *Why no database?* A plan is a pure function of its inputs. Links carry the inputs, so there
  is nothing to persist, and the deploy has fewer moving parts.
- *Why more than 11 hours of driving on one sheet?* The limit is per duty period (between
  10-hour breaks), not per calendar day. The audit checks it per duty period.
- *Why on duty after the 14th hour?* Only driving is prohibited after the 14th hour (FMCSA
  guide, p. 9). Drop-off work can legally finish later.
- *Why OSRM and not a truck router?* It's free and keyless. Its car timings are capped at
  truck speed. Set `ORS_API_KEY` for the heavy-goods-vehicle profile.
