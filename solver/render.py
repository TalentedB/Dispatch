"""Prints a finished simulation in the brief's output format."""

from __future__ import annotations

from .engine import Return, Trip, Vehicle
from .model import BASE, Point, dist


def format_time(minutes: int) -> str:
    return f"{(minutes // 60) % 24:02d}:{minutes % 60:02d}"  # wraps past midnight


def drive_text(start: Point, end: Point) -> str | None:
    parts = []
    dy, dx = end.y - start.y, end.x - start.x
    if dy:
        parts.append(f"{abs(dy)} minutes {'north' if dy > 0 else 'south'}")
    if dx:
        parts.append(f"{abs(dx)} minutes {'east' if dx > 0 else 'west'}")
    return "Drive " + " and ".join(parts) if parts else None


def render(vehicles: list[Vehicle]) -> list[str]:
    events: list[tuple[int, int, int, str]] = []  # (time, vehicle, seq, text)
    for v in vehicles:
        seq = 0

        def emit(time: int, text: str | None) -> None:
            nonlocal seq
            if text:
                events.append((time, v.id, seq, text))
                seq += 1

        for item in v.history:
            if isinstance(item, Trip):
                emit(item.depart_time, "Start route to job")
                emit(item.depart_time, drive_text(item.depart_pos, item.call.location))
                emit(item.arrive_time, "Start job")
                emit(item.finish_time, "Finish job")
            elif isinstance(item, Return):
                emit(item.start_time, "Start route to base")
                emit(item.start_time, drive_text(item.start_pos, BASE))
                home = item.start_time + dist(item.start_pos, BASE)
                if item.interrupted_at is None or home <= item.interrupted_at:
                    emit(home, "Arrive at base")

    events.sort(key=lambda e: (e[0], e[1], e[2]))
    return [f"Vehicle {vid}: {format_time(t)} {text}" for t, vid, _, text in events]
