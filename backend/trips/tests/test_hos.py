"""Hours-of-service engine tests. These run without Django or network access."""

import random
from datetime import datetime

import pytest

from trips.hos import (
    Activity,
    HOSRules,
    Place,
    PlanningError,
    PolylineLeg,
    Status,
    TripSettings,
    build_daily_logs,
    plan_trip,
    validate_plan,
)

CHICAGO, ST_LOUIS, DALLAS = (41.88, -87.63), (38.63, -90.20), (32.78, -96.80)
DEPART_6AM = datetime(2026, 10, 5, 6, 0)


def leg(miles: float, mph: float = 55.0, start=CHICAGO, end=ST_LOUIS) -> PolylineLeg:
    return PolylineLeg.straight(start, end, miles, miles / mph * 60 if miles else 0)


def plan(legs, cycle_hours=0.0, departure=DEPART_6AM, settings=None, **kwargs):
    return plan_trip(
        legs,
        cycle_used_minutes=round(cycle_hours * 60),
        departure_minute_of_day=departure.hour * 60 + departure.minute,
        settings=settings,
        **kwargs,
    )


def activities(segments):
    return [s.activity for s in segments]


def assert_compliant(segments, cycle_hours=0.0, settings=None):
    checks = validate_plan(segments, cycle_used_minutes=round(cycle_hours * 60), settings=settings)
    failed = [f"{c.label}: {c.actual} > {c.limit}" for c in checks if not c.passed]
    assert not failed, failed


def logs_for(segments, departure=DEPART_6AM, cycle_hours=0.0):
    places = [Place("here", "here")] * len(segments)
    return build_daily_logs(
        segments,
        places,
        departure=departure,
        origin=Place("origin", "origin"),
        destination=Place("dest", "dest"),
        cycle_used_minutes=round(cycle_hours * 60),
    )


class TestShortTrip:
    def test_single_day_sequence(self):
        segments = plan([leg(55), leg(110)])
        assert activities(segments) == [
            Activity.PRE_TRIP,
            Activity.DRIVE,
            Activity.PICKUP,
            Activity.DRIVE,
            Activity.DROPOFF,
            Activity.POST_TRIP,
        ]
        assert [s.minutes for s in segments] == [30, 60, 60, 120, 60, 15]
        assert_compliant(segments)

    def test_pickup_and_dropoff_are_one_hour_on_duty(self):
        segments = plan([leg(55), leg(110)])
        for activity in (Activity.PICKUP, Activity.DROPOFF):
            (stop,) = [s for s in segments if s.activity is activity]
            assert stop.status is Status.ON and stop.minutes == 60

    def test_current_location_equals_pickup(self):
        segments = plan([leg(0), leg(110)])
        assert activities(segments)[:2] == [Activity.PRE_TRIP, Activity.PICKUP]
        assert_compliant(segments)

    def test_one_log_sheet_totalling_24_hours(self):
        (log,) = logs_for(plan([leg(55), leg(110)]))
        assert sum(log.totals.values()) == 24 * 60
        assert log.totals[Status.D] == 180
        assert log.totals[Status.ON] == 30 + 60 + 60 + 15
        assert log.miles == pytest.approx(165)


class TestDrivingLimits:
    def test_break_after_eight_hours_of_driving(self):
        segments = plan([leg(0), leg(9 * 55)])
        drives_before_break = []
        for s in segments:
            if s.activity is Activity.BREAK:
                break
            if s.status is Status.D:
                drives_before_break.append(s.minutes)
        assert sum(drives_before_break) == 8 * 60
        (brk,) = [s for s in segments if s.activity is Activity.BREAK]
        assert brk.status is Status.OFF and brk.minutes == 30
        assert_compliant(segments)

    def test_pickup_satisfies_the_30_minute_break(self):
        # 5h to pickup, 1h loading, then 5h more: the hour of loading is the break.
        segments = plan([leg(5 * 55), leg(5 * 55)])
        assert Activity.BREAK not in activities(segments)
        assert_compliant(segments)

    def test_ten_hour_rest_after_eleven_hours_of_driving(self):
        segments = plan([leg(0), leg(14 * 55)])
        rest_index = activities(segments).index(Activity.REST)
        driven = sum(s.minutes for s in segments[:rest_index] if s.status is Status.D)
        assert driven == 11 * 60
        rest = segments[rest_index]
        assert rest.status is Status.SB and rest.minutes == 10 * 60
        assert segments[rest_index - 1].activity is Activity.POST_TRIP
        assert segments[rest_index + 1].activity is Activity.PRE_TRIP
        assert_compliant(segments)

    def test_rest_can_be_logged_off_duty(self):
        segments = plan([leg(0), leg(14 * 55)], settings=TripSettings(rest_in_sleeper=False))
        (rest,) = [s for s in segments if s.activity is Activity.REST]
        assert rest.status is Status.OFF

    def test_fourteen_hour_window_binds_before_eleven_hours(self):
        # Fuel every 100 miles at 50 mph -> 30 min on duty every 2 hours of driving, so the
        # window closes before 11 hours of driving accumulate.
        settings = TripSettings(fuel_interval_miles=100)
        segments = plan([leg(0, 50), leg(1200, 50)], settings=settings)
        assert_compliant(segments, settings=settings)
        window_start = None
        for s in segments:
            if s.activity is Activity.REST:
                window_start = None
            elif s.status.is_on_duty and window_start is None:
                window_start = s.start
            if s.status is Status.D:
                assert s.end - window_start <= 14 * 60

    def test_no_driving_after_14th_hour_even_with_long_stops(self):
        settings = TripSettings(pickup_minutes=6 * 60)
        segments = plan([leg(4 * 55), leg(6 * 55)], settings=settings)
        assert_compliant(segments, settings=settings)


class TestFuel:
    def test_fuel_at_least_every_1000_miles(self):
        segments = plan([leg(400), leg(2500)])
        fuel_miles = [s.miles_start for s in segments if s.activity is Activity.FUEL]
        assert 2 <= len(fuel_miles) <= 3
        checkpoints = [0.0, *fuel_miles, segments[-1].miles_end]
        assert all(b - a <= 1000 for a, b in zip(checkpoints, checkpoints[1:]))
        assert all(s.minutes == 30 and s.status is Status.ON for s in segments if s.activity is Activity.FUEL)

    def test_no_fuel_stop_under_1000_miles(self):
        assert Activity.FUEL not in activities(plan([leg(300), leg(650)]))

    def test_fuel_stop_doubles_as_30_minute_break(self):
        # The 8-hour break falls 600+ miles after the last fill-up, with fuel needed again
        # before arrival: fuel there instead of taking a separate off-duty break.
        segments = plan([leg(0), leg(1500)])
        assert_compliant(segments)
        assert Activity.FUEL in activities(segments)
        for i, s in enumerate(segments[:-1]):
            if s.activity is Activity.FUEL:
                assert segments[i + 1].activity is not Activity.BREAK

    def test_no_fuel_merge_when_the_tank_reaches_the_destination(self):
        assert Activity.FUEL not in activities(plan([leg(100), leg(800)]))


class TestCycle:
    def test_exhausted_cycle_restarts_before_any_driving(self):
        segments = plan([leg(55), leg(110)], cycle_hours=70)
        assert segments[0].activity is Activity.RESTART
        assert segments[0].minutes == 34 * 60
        assert segments[0].cycle_after == 0
        assert_compliant(segments, cycle_hours=70)

    def test_high_cycle_forces_restart_mid_trip(self):
        segments = plan([leg(100), leg(700)], cycle_hours=66)
        assert Activity.RESTART in activities(segments)
        assert_compliant(segments, cycle_hours=66)

    def test_low_cycle_needs_no_restart(self):
        assert Activity.RESTART not in activities(plan([leg(300), leg(650)], cycle_hours=20))

    def test_restart_choice_is_never_slower_than_greedy(self):
        rng = random.Random(7)
        for _ in range(60):
            legs = [leg(rng.uniform(0, 600)), leg(rng.uniform(50, 2500))]
            cycle = rng.uniform(40, 70)
            smart = plan(legs, cycle_hours=cycle)
            greedy = plan(legs, cycle_hours=cycle, branch_depth=0)
            assert smart[-1].end <= greedy[-1].end
            assert_compliant(smart, cycle_hours=cycle)

    def test_restart_is_taken_early_instead_of_wasting_a_rest(self):
        # 3.5 cycle hours left at the end of the shift: a 10-hour rest would buy ~2.5 hours
        # of driving before a restart anyway, so restarting immediately delivers sooner.
        segments = plan([leg(0), leg(1500)], cycle_hours=55)
        first_off = next(s for s in segments if s.activity in (Activity.REST, Activity.RESTART))
        assert first_off.activity is Activity.RESTART


class TestDailyLogs:
    def test_multi_day_sheets(self):
        segments = plan([leg(300), leg(2000)], cycle_hours=10)
        logs = logs_for(segments, cycle_hours=10)
        assert len(logs) >= 3
        for log in logs:
            assert sum(log.totals.values()) == 24 * 60
            assert log.lines[0].start == 0 and log.lines[-1].end == 24 * 60
            assert all(a.end == b.start for a, b in zip(log.lines, log.lines[1:]))
            assert all(a.status != b.status for a, b in zip(log.lines, log.lines[1:]))
        assert sum(log.miles for log in logs) == pytest.approx(2300, abs=0.01)
        assert [log.day for log in logs] == list(range(1, len(logs) + 1))

    def test_first_sheet_starts_off_duty_until_departure(self):
        logs = logs_for(plan([leg(55), leg(110)]))
        assert logs[0].lines[0].status is Status.OFF
        assert logs[0].lines[0].end == 6 * 60
        assert logs[0].remarks[0].minute == 6 * 60
        assert logs[0].remarks[0].activity is Activity.PRE_TRIP

    def test_last_sheet_ends_off_duty_with_trip_complete_remark(self):
        logs = logs_for(plan([leg(55), leg(110)]))
        assert logs[-1].lines[-1].status is Status.OFF
        assert logs[-1].remarks[-1].note == "Off duty - trip complete"

    def test_remark_for_every_change_of_status(self):
        for log in logs_for(plan([leg(300), leg(1400)])):
            remark_minutes = {r.minute for r in log.remarks}
            for line in log.lines[1:]:
                assert line.start in remark_minutes

    def test_recap_tracks_the_70_hour_window(self):
        segments = plan([leg(300), leg(650)], cycle_hours=20)
        logs = logs_for(segments, cycle_hours=20)
        on_duty_trip = sum(s.minutes for s in segments if s.status.is_on_duty)
        assert logs[-1].cycle_total == 20 * 60 + on_duty_trip
        assert logs[-1].available_tomorrow == 70 * 60 - logs[-1].cycle_total
        assert sum(log.on_duty_today for log in logs) == on_duty_trip

    def test_recap_resets_after_restart(self):
        segments = plan([leg(55), leg(110)], cycle_hours=70)
        logs = logs_for(segments, cycle_hours=70)
        restart_day = next(log for log in logs if log.restart_completed)
        on_duty_after = sum(s.minutes for s in segments if s.status.is_on_duty)
        assert logs[-1].cycle_total == on_duty_after
        assert restart_day.available_tomorrow <= 70 * 60

    def test_departure_near_midnight_splits_driving_exactly(self):
        departure = datetime(2026, 10, 5, 23, 30)
        segments = plan([leg(55), leg(400)], departure=departure)
        logs = logs_for(segments, departure=departure)
        assert len(logs) == 2
        assert sum(log.miles for log in logs) == pytest.approx(455)
        assert all(sum(log.totals.values()) == 1440 for log in logs)


class TestValidation:
    def test_rejects_cycle_over_70(self):
        with pytest.raises(PlanningError):
            plan([leg(55), leg(110)], cycle_hours=70.5)

    def test_rejects_break_shorter_than_30_minutes(self):
        with pytest.raises(PlanningError):
            plan([leg(55), leg(110)], settings=TripSettings(break_minutes=15))

    @staticmethod
    def _without(segments, removed, keep_first=True):
        """Delete segments and close the gaps, as a sloppy planner might."""
        kept, shift = [], 0
        for s in segments:
            if s.activity in removed and (s.start > 0 or not keep_first):
                shift += s.minutes
                continue
            s.start -= shift
            s.end -= shift
            kept.append(s)
        return kept

    def test_validator_flags_missing_ten_hour_rest(self):
        segments = plan([leg(0), leg(14 * 55)])
        tampered = self._without(segments, {Activity.REST, Activity.POST_TRIP, Activity.PRE_TRIP})
        failed = {c.id for c in validate_plan(tampered, cycle_used_minutes=0) if not c.passed}
        assert failed == {"driving_limit", "duty_window"}

    def test_validator_flags_missing_30_minute_break(self):
        segments = plan([leg(0), leg(9 * 55)])
        tampered = self._without(segments, {Activity.BREAK})
        failed = {c.id for c in validate_plan(tampered, cycle_used_minutes=0) if not c.passed}
        assert failed == {"rest_break"}

    def test_validator_flags_cycle_overrun(self):
        segments = plan([leg(55), leg(400)], cycle_hours=66)
        assert segments[0].activity is Activity.RESTART
        tampered = self._without(segments, {Activity.RESTART}, keep_first=False)
        failed = {c.id for c in validate_plan(tampered, cycle_used_minutes=66 * 60) if not c.passed}
        assert "cycle_limit" in failed


@pytest.mark.parametrize("seed", range(400))
def test_random_trips_are_always_compliant(seed):
    rng = random.Random(seed)
    legs = [
        leg(rng.choice([0, rng.uniform(1, 800)]), rng.uniform(25, 68)),
        leg(rng.uniform(1, 3200), rng.uniform(25, 68)),
    ]
    cycle = rng.choice([0, 70, rng.uniform(0, 70)])
    departure = datetime(2026, 3, 1, rng.randrange(24), rng.randrange(0, 60, 5))
    segments = plan(legs, cycle_hours=cycle, departure=departure)
    assert_compliant(segments, cycle_hours=cycle)
    logs = logs_for(segments, departure=departure, cycle_hours=cycle)
    assert all(sum(log.totals.values()) == 1440 for log in logs)
    total_miles = legs[0].total_miles + legs[1].total_miles
    assert sum(log.miles for log in logs) == pytest.approx(total_miles, abs=0.01)
    assert segments[-1].miles_end == pytest.approx(total_miles, abs=0.01)
    assert all(s.end > s.start for s in segments)


def test_rules_constants_match_49_cfr_395():
    rules = HOSRules()
    assert (rules.max_driving, rules.duty_window, rules.driving_before_break) == (660, 840, 480)
    assert (rules.cycle_limit, rules.reset_off_duty, rules.restart_off_duty) == (4200, 600, 2040)
