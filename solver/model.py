"""Core types, grid geometry and input parsing.

Coordinates are relative to the base at (0, 0): +x is east, +y is north.
One block takes one minute to drive.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Point:
    x: int
    y: int


BASE = Point(0, 0)


def dist(a: Point, b: Point) -> int:
    """Manhattan distance = travel minutes."""
    return abs(a.x - b.x) + abs(a.y - b.y)


def _sign(n: int) -> int:
    return (n > 0) - (n < 0)


def position_along(start: Point, end: Point, elapsed: int) -> Point:
    """Position after `elapsed` minutes driving from start to end.

    Vehicles drive the north/south leg first, then east/west, matching the
    order drive instructions are printed in.
    """
    dy = end.y - start.y
    if elapsed <= abs(dy):
        return Point(start.x, start.y + _sign(dy) * elapsed)
    elapsed -= abs(dy)
    dx = end.x - start.x
    if elapsed <= abs(dx):
        return Point(start.x + _sign(dx) * elapsed, end.y)
    return end


@dataclass(frozen=True)
class Call:
    index: int  # position in the input file, used to break ties deterministically
    time: int  # minutes since midnight
    location: Point
    duration: int


class InputError(ValueError):
    pass


_TIME = re.compile(r"(\d{1,2}):(\d{2})")
_TOKEN = re.compile(r"\d+|[A-Za-z]+|\S")  # "15N" splits like "15 N"


def _parse_call(line: str, index: int) -> Call:
    head, _, rest = line.partition(" ")
    m = _TIME.fullmatch(head)
    if not m or int(m[1]) > 23 or int(m[2]) > 59:
        raise ValueError(f"bad time {head!r}")
    tokens = _TOKEN.findall(rest)
    if not tokens or not tokens[-1].isdigit():
        raise ValueError("missing job duration")
    body = tokens[:-1]
    if len(body) % 2:
        raise ValueError("each distance needs a direction")
    x = y = None
    for amount, direction in zip(body[::2], body[1::2]):
        d = direction.upper()
        if not amount.isdigit() or d not in ("N", "S", "E", "W"):
            raise ValueError(f"bad distance {amount!r} {direction!r}")
        if d in ("N", "S"):
            if y is not None:
                raise ValueError("two north/south distances")
            y = int(amount) if d == "N" else -int(amount)
        else:
            if x is not None:
                raise ValueError("two east/west distances")
            x = int(amount) if d == "E" else -int(amount)
    return Call(index, int(m[1]) * 60 + int(m[2]), Point(x or 0, y or 0), int(tokens[-1]))


def parse_input(text: str) -> tuple[int, list[Call]]:
    """Returns (vehicle count, calls in file order). Blank lines and # comments are ignored."""
    lines = [(no, raw.split("#", 1)[0].strip()) for no, raw in enumerate(text.splitlines(), 1)]
    lines = [(no, line) for no, line in lines if line]
    if not lines or not lines[0][1].isdigit() or int(lines[0][1]) < 1:
        raise InputError("first line must be the number of vehicles (>= 1)")
    calls = []
    for index, (no, line) in enumerate(lines[1:]):
        try:
            calls.append(_parse_call(line, index))
        except ValueError as e:
            raise InputError(f"line {no}: {e}: {line!r}") from None
    return int(lines[0][1]), calls
