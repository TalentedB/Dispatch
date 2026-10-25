import importlib.util
from pathlib import Path

import pytest

from solver.__main__ import MODES, make_algorithm
from solver.engine import run
from solver.model import parse_input
from solver.render import render

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("export_viz", ROOT / "tools" / "export_viz.py")
export_viz = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(export_viz)

ALL_INPUTS = sorted((ROOT / "inputs").glob("*.txt")) + sorted((ROOT / "inputs" / "generated").glob("*.txt"))


def trace_for(path: Path, mode: str) -> dict:
    text = path.read_text()
    output = "\n".join(render(run(*parse_input(text), make_algorithm(mode))))
    return export_viz.build_trace(mode, path.stem, text, output)


def path_length(path):
    return sum(abs(a[0] - b[0]) + abs(a[1] - b[1]) for a, b in zip(path, path[1:]))


def test_brief_small_redirect_starts_where_the_return_was_cut():
    segs = trace_for(ROOT / "inputs" / "brief_small.txt", "greedy")["vehicles"][0]["segments"]
    kinds = [s["kind"] for s in segs]
    assert kinds == ["to_job", "on_job", "to_base", "to_job", "on_job", "to_base"]
    assert segs[2]["interrupted"] and segs[2]["end"] == 12 * 60 + 8
    assert segs[3]["path"] == [[4, 0], [6, 0]]
    assert segs[3]["callId"] == 1


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("path", ALL_INPUTS, ids=lambda p: p.stem)
def test_trace_is_consistent(path, mode):
    trace = trace_for(path, mode)
    assert trace["check"]["valid"], trace["check"]["errors"]
    served = []
    for v in trace["vehicles"]:
        prev_end = None
        for s in v["segments"]:
            assert s["start"] <= s["end"]
            if prev_end is not None:
                assert s["start"] == prev_end or s["start"] > prev_end
            prev_end = s["end"]
            if s["kind"] in ("to_job", "to_base") and not s.get("interrupted"):
                assert path_length(s["path"]) == s["end"] - s["start"]
            if s["kind"] == "to_job":
                served.append(s["callId"])
    assert sorted(served) == [c["id"] for c in trace["calls"]]
