"""Checks a solver's printed schedule against the rules, and scores it.

The checker replays the output line by line, tracking where every vehicle is,
and reports anything impossible or against the brief:

  * lines that aren't in the 'Vehicle N: HH:MM <action>' format
  * lines out of chronological order
  * a vehicle leaving for a call before the call came in
  * a drive that doesn't lead to an open call, or a wrong drive back to base
  * wrong timing (arrival vs. drive length, finish vs. job duration)
  * switching to a new job while driving to or working another one
  * calls never served, vehicles never returning to base

It does not decide *how* a vehicle should be scheduled. Any valid choice is
accepted, including which axis a vehicle drives first: a vehicle redirected
on its way home may be anywhere on a shortest path back to base.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from .inputs import BASE, Call, Point, manhattan, parse_clock

MAX_ERRORS = 50

_LINE = re.compile(r"Vehicle\s+(\d+)\s*:\s*(\d{1,2}:\d{2})\s+(.+)", re.IGNORECASE)
_DRIVE = re.compile(
    r"drive (\d+) minutes? (north|south|east|west)(?: and (\d+) minutes? (north|south|east|west))?"
)
_ACTIONS = {"start route to job", "start route to base", "start job", "finish job", "arrive at base"}
_COVERAGE_ACTIONS = {"start route to staging", "arrive at staging"}
_STEP = {"north": (0, 1), "south": (0, -1), "east": (1, 0), "west": (-1, 0)}


def fmt_time(t: int) -> str:
    days = f" (+{t // 1440}d)" if t >= 1440 else ""
    return f"{(t // 60) % 24:02d}:{t % 60:02d}{days}"


def fmt_point(p: Point) -> str:
    if p == BASE:
        return "base"
    parts = []
    if p.y:
        parts.append(f"{abs(p.y)} {'N' if p.y > 0 else 'S'}")
    if p.x:
        parts.append(f"{abs(p.x)} {'E' if p.x > 0 else 'W'}")
    return " ".join(parts)


def fmt_drive(d: Point) -> str:
    return "nothing" if d == BASE else fmt_point(d)


@dataclass(frozen=True)
class Event:
    line_no: int
    vehicle: int
    time: int  # absolute minutes; can exceed 24h if the schedule runs past midnight
    action: str  # one of _ACTIONS, or "drive"
    delta: Point | None = None  # for "drive"


@dataclass(frozen=True)
class Metrics:
    calls_served: int
    avg_response: float  # mean minutes from call arriving to vehicle starting the job
    max_response: int
    avg_delay: float  # mean response minus the drive time from base (time lost to busy vehicles)
    total_drive: int  # minutes driven by the whole fleet, including returns to base
    vehicles_used: int
    last_return: int  # absolute minute the last vehicle got back to base

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class CheckResult:
    errors: list[str] = field(default_factory=list)
    metrics: Metrics | None = None

    @property
    def valid(self) -> bool:
        return not self.errors


def parse_output(text: str, errors: list[str]) -> list[Event]:
    events: list[Event] = []
    days = 0
    latest: int | None = None
    for line_no, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        m = _LINE.fullmatch(line)
        if not m:
            errors.append(f"output line {line_no}: not in 'Vehicle N: HH:MM <action>' format: {line!r}")
            continue
        try:
            t = parse_clock(m[2]) + 1440 * days
        except ValueError as e:
            errors.append(f"output line {line_no}: {e}")
            continue
        if latest is not None and t < latest:
            if latest - t > 12 * 60:  # clock wrapped past midnight
                days += 1
                t += 1440
            else:
                errors.append(f"output line {line_no}: time goes backwards ({fmt_time(latest)} -> {m[2]}); "
                              "output must be in chronological order")
        latest = t if latest is None else max(latest, t)

        vehicle = int(m[1])
        action = " ".join(m[3].lower().split())
        if action in _ACTIONS | _COVERAGE_ACTIONS:
            events.append(Event(line_no, vehicle, t, action))
            continue
        d = _DRIVE.fullmatch(action)
        if not d:
            errors.append(f"output line {line_no}: unknown action {m[3]!r}")
            continue
        if d[4] and (d[2] in ("north", "south")) == (d[4] in ("north", "south")):
            errors.append(f"output line {line_no}: drive mentions the same axis twice: {m[3]!r}")
            continue
        dx = dy = 0
        for amount, direction in ((d[1], d[2]), (d[3], d[4])):
            if amount:
                sx, sy = _STEP[direction]
                dx, dy = dx + sx * int(amount), dy + sy * int(amount)
        events.append(Event(line_no, vehicle, t, "drive", Point(dx, dy)))
    return events


def _along(start: Point, elapsed: int, ns_first: bool) -> Point:
    """Position after `elapsed` minutes driving from start toward base, one axis at a time."""
    x, y = start.x, start.y
    for axis in (("y", "x") if ns_first else ("x", "y")):
        value = y if axis == "y" else x
        step = min(abs(value), elapsed)
        elapsed -= step
        value -= step if value > 0 else -step
        if axis == "y":
            y = value
        else:
            x = value
    return Point(x, y)


def _upcoming_job_length(events: list[Event], start_index: int, vehicle: int) -> int | None:
    """Length of the job this vehicle does after the route starting at start_index, if printed."""
    started = None
    for e in events[start_index + 1:]:
        if e.vehicle != vehicle:
            continue
        if e.action == "start job":
            started = e.time
        elif e.action == "finish job" and started is not None:
            return e.time - started
        elif e.action.startswith("start route"):
            return None
    return None


@dataclass
class _Vehicle:
    mode: str = "base"  # base | to_job | on_job | done_at_job | to_base | broken
    pos: Point = BASE  # base/done_at_job: where it is; to_base: where the return trip started
    since: int = 0  # when the current mode began
    due: int = 0  # to_job: arrival; on_job: finish; to_base: arrival at base
    call: Call | None = None
    pending: Event | None = None  # a 'Start route to ...' waiting for its Drive line
    jobs: int = 0
    destination: Point = BASE  # optional staging route endpoint


def check(num_vehicles: int, calls: list[Call], output: str, *, allow_reposition: bool = False) -> CheckResult:
    errors: list[str] = []
    events = parse_output(output, errors)
    vehicles: dict[int, _Vehicle] = {}
    open_calls = sorted(calls, key=lambda c: (c.time, c.index))
    started: dict[int, int] = {}  # call index -> time the job started
    total_drive = 0
    last_return = 0

    def fail(e: Event, msg: str, v: _Vehicle) -> None:
        errors.append(f"output line {e.line_no} (vehicle {e.vehicle} at {fmt_time(e.time)}): {msg}"
                      " [later lines for this vehicle not checked]")
        v.mode = "broken"

    def finish_route(v: _Vehicle, start: Event, delta: Point) -> None:
        nonlocal total_drive
        def staging_position() -> Point:
            elapsed = start.time - v.since
            dx, dy = v.destination.x - v.pos.x, v.destination.y - v.pos.y
            xs = min(abs(dx), elapsed)
            ys = min(abs(dy), max(0, elapsed - abs(dx)))
            return Point(v.pos.x + (1 if dx >= 0 else -1) * xs,
                         v.pos.y + (1 if dy >= 0 else -1) * ys)

        if start.action == "start route to staging":
            origin = v.pos
            if v.mode == "to_staging":
                origin = staging_position()
                total_drive += start.time - v.since
            elif v.mode == "to_base":
                # Coverage is an opt-in extension with an explicit x-first route.
                v.destination = BASE
                origin = staging_position()
                total_drive += start.time - v.since
            v.pos, v.destination = origin, Point(origin.x + delta.x, origin.y + delta.y)
            v.mode, v.since, v.due = "to_staging", start.time, start.time + manhattan(BASE, delta)
            return
        if start.action == "start route to base":
            if v.mode == "to_staging":
                total_drive += start.time - v.since
                v.pos = staging_position()
            home = Point(-v.pos.x, -v.pos.y)
            if delta != home:
                return fail(start, f"route to base from {fmt_point(v.pos)} drives {fmt_drive(delta)}, "
                                   f"should be {fmt_drive(home)}", v)
            v.mode, v.since, v.due = "to_base", start.time, start.time + manhattan(v.pos, BASE)
            return

        t = start.time
        if v.mode == "to_staging":
            here = staging_position()
            usual = [here]

            def possible(p: Point) -> bool:
                return p == here
            where = f"at {fmt_point(here)} during staging"
        elif v.mode == "to_base":
            # Redirected on the way home: it can be anywhere on a shortest path to base.
            elapsed, total = t - v.since, manhattan(v.pos, BASE)
            return_from = v.pos
            usual = [_along(return_from, elapsed, ns_first=True), _along(return_from, elapsed, ns_first=False)]

            def possible(p: Point) -> bool:
                return manhattan(return_from, p) == elapsed and manhattan(p, BASE) == total - elapsed
            where = f"{elapsed} min into its drive home from {fmt_point(return_from)}"
        else:
            here = v.pos
            usual = [here]

            def possible(p: Point) -> bool:
                return p == here
            where = f"at {fmt_point(here)}"

        def origin(c: Call) -> Point:
            return Point(c.location.x - delta.x, c.location.y - delta.y)

        candidates = [c for c in open_calls if possible(origin(c))]
        ready = [c for c in candidates if c.time <= t]
        if not ready:
            if candidates:
                return fail(start, f"leaves for call #{candidates[0].index} at {fmt_time(t)} but the call "
                                   f"only comes in at {fmt_time(candidates[0].time)}", v)
            return fail(start, f"vehicle is {where}; driving {fmt_drive(delta)} doesn't reach any open call", v)

        # Several calls can fit the same drive (e.g. two places reachable from different
        # points on the way home). Use the job length printed later to tell them apart,
        # then prefer the usual N/S-first / E/W-first route, then the earliest call.
        duration = _upcoming_job_length(events, index_of[id(start)], start.vehicle)
        if duration is not None and any(c.duration == duration for c in ready):
            ready = [c for c in ready if c.duration == duration]
        match = min(ready, key=lambda c: (usual.index(origin(c)) if origin(c) in usual else len(usual),
                                          c.time, c.index))

        if v.mode in ("to_base", "to_staging"):
            total_drive += t - v.since
        total_drive += manhattan(BASE, delta)
        open_calls.remove(match)
        v.mode, v.call, v.since, v.due = "to_job", match, t, t + manhattan(BASE, delta)

    index_of = {id(e): i for i, e in enumerate(events)}
    for e in events:
        if not 0 <= e.vehicle < num_vehicles:
            errors.append(f"output line {e.line_no}: vehicle {e.vehicle} doesn't exist "
                          f"(fleet is vehicles 0-{num_vehicles - 1})")
            continue
        v = vehicles.setdefault(e.vehicle, _Vehicle())
        if v.mode == "broken":
            continue
        if e.action in _COVERAGE_ACTIONS and not allow_reposition:
            fail(e, "staging output requires allow_reposition=True", v)
            continue
        if v.pending and e.action != "drive":
            # 'Start route' with no Drive line: a zero-length trip.
            pending, v.pending = v.pending, None
            finish_route(v, pending, BASE)
            if v.mode == "broken":
                continue

        if e.action == "start route to job":
            if v.mode in ("to_job", "on_job"):
                fail(e, f"starts a new route while still handling call #{v.call.index} "
                        "(vehicles can't switch jobs)", v)
            elif v.mode in ("to_base", "to_staging") and e.time >= v.due:
                fail(e, f"should have printed 'Arrive at base' at {fmt_time(v.due)} first", v)
            else:
                v.pending = e
        elif e.action == "start route to base":
            if v.mode != "done_at_job" and not (allow_reposition and v.mode in ("staging", "to_staging")):
                fail(e, "starts a route to base without having just finished a job", v)
            else:
                v.pending = e
        elif e.action == "start route to staging":
            if v.mode in ("to_job", "on_job"):
                fail(e, "staging cannot override a committed job", v)
            elif v.mode in ("to_staging", "to_base") and e.time >= v.due:
                fail(e, "missing arrival before staging route", v)
            else:
                v.pending = e
        elif e.action == "drive":
            if not v.pending or v.pending.time != e.time:
                fail(e, "Drive line without a 'Start route to ...' line just before it", v)
            else:
                pending, v.pending = v.pending, None
                finish_route(v, pending, e.delta)
        elif e.action == "start job":
            if v.mode != "to_job":
                fail(e, "starts a job without having driven to one", v)
            elif e.time != v.due:
                fail(e, f"starts call #{v.call.index} at {fmt_time(e.time)} but the drive gets there at "
                        f"{fmt_time(v.due)}", v)
            else:
                started[v.call.index] = e.time
                v.mode, v.since, v.due = "on_job", e.time, e.time + v.call.duration
        elif e.action == "finish job":
            if v.mode != "on_job":
                fail(e, "finishes a job it never started", v)
            elif e.time != v.due:
                fail(e, f"finishes call #{v.call.index} at {fmt_time(e.time)} but a {v.call.duration}-min job "
                        f"started at {fmt_time(v.since)} ends at {fmt_time(v.due)}", v)
            else:
                v.mode, v.pos, v.since, v.jobs = "done_at_job", v.call.location, e.time, v.jobs + 1
        elif e.action == "arrive at base":
            if v.mode != "to_base":
                fail(e, "arrives at base without driving there", v)
            elif e.time != v.due:
                fail(e, f"arrives at base at {fmt_time(e.time)} but the drive gets there at {fmt_time(v.due)}", v)
            else:
                total_drive += manhattan(v.pos, BASE)
                last_return = max(last_return, e.time)
                v.mode, v.pos, v.since = "base", BASE, e.time
        elif e.action == "arrive at staging":
            if v.mode != "to_staging" or e.time != v.due:
                fail(e, "incorrect staging arrival time/state", v)
            else:
                total_drive += manhattan(v.pos, v.destination)
                v.mode = "base" if v.destination == BASE else "staging"
                v.pos, v.since = v.destination, e.time

    for vid, v in sorted(vehicles.items()):
        if v.pending:
            pending, v.pending = v.pending, None
            finish_route(v, pending, BASE)
        problem = {
            "to_job": "never starts the job it was driving to",
            "on_job": "never finishes its last job",
            "done_at_job": "never returns to base after its last job",
            "to_base": "never prints 'Arrive at base'",
            "to_staging": "never finishes staging or returns to base",
            "staging": "never returns to base from staging",
        }.get(v.mode)
        if allow_reposition and v.mode in ("done_at_job", "staging"):
            # Coverage mode may end with free vehicles resting off base. An
            # unfinished drive or service is still invalid in every mode.
            problem = None
        if problem:
            errors.append(f"vehicle {vid}: {problem}")

    for c in open_calls:
        errors.append(f"call #{c.index} ({fmt_time(c.time)} at {fmt_point(c.location)}) is never served")

    served = [c for c in calls if c.index in started]
    responses = [started[c.index] - c.time for c in served]
    delays = [r - manhattan(BASE, c.location) for r, c in zip(responses, served)]
    n = len(served)
    metrics = Metrics(
        calls_served=n,
        avg_response=sum(responses) / n if n else 0.0,
        max_response=max(responses, default=0),
        avg_delay=sum(delays) / n if n else 0.0,
        total_drive=total_drive,
        vehicles_used=sum(1 for v in vehicles.values() if v.jobs),
        last_return=last_return,
    )

    if len(errors) > MAX_ERRORS:
        errors = errors[:MAX_ERRORS] + [f"... and {len(errors) - MAX_ERRORS} more errors"]
    return CheckResult(errors, metrics)
