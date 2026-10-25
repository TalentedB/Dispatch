import sys
from pathlib import Path

from bench import run_one
from tester.runner import build_argv, load_solvers

FIXTURES = Path(__file__).resolve().parent / "fixtures"
INPUTS = Path(__file__).resolve().parent.parent / "inputs"
PY = sys.executable


def test_build_argv_placeholder_and_append():
    p = Path("inputs/x.txt")
    assert build_argv("python3 s.py {input} --fast", p) == ["python3", "s.py", "inputs/x.txt", "--fast"]
    assert build_argv("python3 s.py", p) == ["python3", "s.py", "inputs/x.txt"]


def test_load_solvers(tmp_path):
    f = tmp_path / "solvers.txt"
    f.write_text("# comment\n\ngreedy = python3 a.py {input}\nfast=python3 b.py\n")
    assert load_solvers(f) == {"greedy": "python3 a.py {input}", "fast": "python3 b.py"}


def test_correct_solver_passes_and_matches_expected():
    for expected in INPUTS.glob("*.expected"):
        r = run_one("echo", f"{PY} {FIXTURES / 'echo_expected.py'}", expected.with_suffix(".txt"), timeout=10)
        assert r.status == "ok", r.detail
        assert r.matches_expected is True


def test_crash_and_timeout_are_reported():
    path = INPUTS / "brief_small.txt"
    crashed = run_one("crash", f"{PY} {FIXTURES / 'crash.py'}", path, timeout=10)
    assert crashed.status == "CRASH" and "exploded" in crashed.detail
    hung = run_one("hang", f"{PY} {FIXTURES / 'hang.py'}", path, timeout=0.5)
    assert hung.status == "TIMEOUT"
