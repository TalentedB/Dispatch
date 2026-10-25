"""Reads input files in the brief's format.

    2                    <- number of vehicles
    10:45 15 N 20 W 45   <- HH:MM, distance + N/S, distance + E/W, job minutes
    16:02 4 E 15         <- one axis may be omitted

Blank lines and anything after a '#' are ignored.
Coordinates are relative to the base at (0, 0): +x is east, +y is north.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Point:
    x: int
    y: int


BASE = Point(0, 0)


def manhattan(a: Point, b: Point) -> int:
    return abs(a.x - b.x) + abs(a.y - b.y)


@dataclass(frozen=True)
class Call:
    index: int  # 0-based position in the input file
    time: int  # minutes since midnight
    location: Point
    duration: int


class InputError(ValueError):
    pass


_TIME = re.compile(r"(\d{1,2}):(\d{2})")
_TOKEN = re.compile(r"\d+|[A-Za-z]+|\S")  # splits "15N" like "15 N"


def parse_clock(text: str) -> int:
    match = _TIME.fullmatch(text)
    if not match or int(match[1]) > 23 or int(match[2]) > 59:
        raise ValueError(f"bad time {text!r}, expected HH:MM")
    return int(match[1]) * 60 + int(match[2])


def _parse_call(line: str, index: int) -> Call:
    head, _, rest = line.partition(" ")
    time = parse_clock(head)
    tokens = _TOKEN.findall(rest)
    if not tokens or not tokens[-1].isdigit():
        raise ValueError("missing job duration at end of line")
    body = tokens[:-1]
    if len(body) % 2:
        raise ValueError("each distance needs a direction (N/S/E/W)")

    x = y = None
    for amount, direction in zip(body[::2], body[1::2]):
        d = direction.upper()
        if not amount.isdigit() or d not in ("N", "S", "E", "W"):
            raise ValueError(f"expected '<distance> <N|S|E|W>', got {amount!r} {direction!r}")
        if d in ("N", "S"):
            if y is not None:
                raise ValueError("more than one north/south distance")
            y = int(amount) if d == "N" else -int(amount)
        else:
            if x is not None:
                raise ValueError("more than one east/west distance")
            x = int(amount) if d == "E" else -int(amount)
    return Call(index, time, Point(x or 0, y or 0), int(tokens[-1]))


def parse_input(text: str) -> tuple[int, list[Call]]:
    """Returns (number of vehicles, calls in file order)."""
    lines = [(no, raw.split("#", 1)[0].strip()) for no, raw in enumerate(text.splitlines(), 1)]
    lines = [(no, line) for no, line in lines if line]
    if not lines:
        raise InputError("input is empty")

    first_no, first = lines[0]
    if not first.isdigit() or int(first) < 1:
        raise InputError(f"line {first_no}: expected a vehicle count >= 1, got {first!r}")

    calls = []
    for index, (no, line) in enumerate(lines[1:]):
        try:
            calls.append(_parse_call(line, index))
        except ValueError as e:
            raise InputError(f"line {no}: {e}: {line!r}") from None
    return int(first), calls


def read_input(path: str) -> tuple[int, list[Call]]:
    with open(path) as f:
        return parse_input(f.read())
