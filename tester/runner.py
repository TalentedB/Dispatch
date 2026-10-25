"""Runs solver programs and compares their output with expected answers."""

from __future__ import annotations

import difflib
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOLVERS_FILE = ROOT / "solvers.txt"


@dataclass(frozen=True)
class RunOutcome:
    stdout: str
    stderr: str
    returncode: int | None  # None if it timed out
    seconds: float

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def load_solvers(path: Path = SOLVERS_FILE) -> dict[str, str]:
    """Reads 'name = command' lines. Blank lines and '#' comments are ignored."""
    solvers: dict[str, str] = {}
    if not path.exists():
        return solvers
    for line_no, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name, sep, command = line.partition("=")
        if not sep or not name.strip() or not command.strip():
            raise ValueError(f"{path.name} line {line_no}: expected 'name = command', got {raw!r}")
        solvers[name.strip()] = command.strip()
    return solvers


def build_argv(command: str, input_path: Path) -> list[str]:
    """Substitutes {input} with the input path, or appends it if there's no placeholder."""
    parts = shlex.split(command)
    if any("{input}" in p for p in parts):
        return [p.replace("{input}", str(input_path)) for p in parts]
    return parts + [str(input_path)]


def run_solver(command: str, input_path: Path, timeout: float) -> RunOutcome:
    start = time.perf_counter()
    try:
        proc = subprocess.run(build_argv(command, input_path), cwd=ROOT, capture_output=True,
                              text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        out = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        return RunOutcome(out, f"timed out after {timeout}s", None, time.perf_counter() - start)
    except OSError as e:
        return RunOutcome("", f"couldn't start solver: {e}", -1, time.perf_counter() - start)
    return RunOutcome(proc.stdout, proc.stderr, proc.returncode, time.perf_counter() - start)


def _normalize(text: str) -> list[str]:
    return [" ".join(line.split()) for line in text.splitlines() if line.strip()]


def expected_path(input_path: Path) -> Path:
    return input_path.with_suffix(".expected")


def matches_expected(output: str, input_path: Path) -> bool | None:
    """True/False against the .expected file, or None if there isn't one."""
    exp = expected_path(input_path)
    if not exp.exists():
        return None
    return _normalize(output) == _normalize(exp.read_text())


def expected_diff(output: str, input_path: Path) -> list[str]:
    exp = expected_path(input_path)
    return list(difflib.unified_diff(_normalize(exp.read_text()), _normalize(output),
                                     fromfile="expected", tofile="solver", lineterm=""))
