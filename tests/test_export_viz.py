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


@pytest.mark.parametrize("path", ALL_INPUTS, ids=lambda path: path.stem)
def test_native_dispatch_trace_has_exact_calls_and_continuous_physical_paths(path):
    from dispatch.optimizer import SolverConfig
    from dispatch.simulation import SimulationConfig, simulate
    from dispatch.trace import build_trace
    from tester.inputs import parse_input as parse_dispatch_input

    result = simulate(
        *parse_dispatch_input(path.read_text()),
        SimulationConfig(solver=SolverConfig(0.25)),
    )
    trace = build_trace(result, path.stem)
    assert trace["check"]["valid"]
    served = []
    for vehicle in trace["vehicles"]:
        previous_position, previous_end = [0, 0], result.start_time
        for segment in vehicle["segments"]:
            assert segment["start"] >= previous_end
            assert segment["path"][0] == previous_position
            if segment["kind"] == "on_job":
                emergency = result.emergencies[segment["callId"]]
                assert segment["start"] == emergency.start >= emergency.call.time
                assert segment["end"] - segment["start"] == emergency.call.duration
                served.append(segment["callId"])
            else:
                assert path_length(segment["path"]) == segment["end"] - segment["start"]
                assert all(a[0] == b[0] or a[1] == b[1]
                           for a, b in zip(segment["path"], segment["path"][1:]))
            previous_position, previous_end = segment["path"][-1], segment["end"]
        assert not any(segment["kind"] == "to_base" for segment in vehicle["segments"])
    assert sorted(served) == sorted(result.emergencies)
    assert trace["metrics"]["avg_response"] == result.metrics()["average_response"]
    assert trace["metrics"]["total_drive"] == result.metrics()["total_travel"]
    assert trace["dispatch"]["mapHistory"] == result.map_history


def test_incremental_export_connects_native_dispatch_without_removing_legacy_traces(tmp_path, monkeypatch):
    import json

    monkeypatch.setattr(export_viz, "load_solvers", lambda: {
        "greedy": "python -m solver {input}",
        "strategy4": "python -m dispatch {input}",
    })
    marker = tmp_path / "keep.txt"
    marker.write_text("unrelated file")
    arguments = ["--inputs", str(ROOT / "inputs" / "brief_small.txt"), "--out", str(tmp_path)]
    assert export_viz.main(arguments + ["--only", "greedy"]) == 0
    assert export_viz.main(arguments + ["--only", "strategy4"]) == 0
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert set(manifest["algorithms"]) == {"greedy", "strategy4"}
    scenario = manifest["scenarios"][0]
    native = json.loads((tmp_path / scenario["traces"]["strategy4"]).read_text())
    assert native["check"]["valid"]
    assert native["metrics"]["computation_seconds"] > 0
    assert any(segment["kind"] == "reposition"
               for vehicle in native["vehicles"] for segment in vehicle["segments"])
    assert (tmp_path / scenario["traces"]["greedy"]).exists()
    assert marker.read_text() == "unrelated file"


def test_export_failure_returns_nonzero_and_does_not_advertise_stale_trace(tmp_path, monkeypatch):
    import json

    monkeypatch.setattr(export_viz, "load_solvers", lambda: {
        "broken": "python tests/fixtures/crash.py {input}",
    })
    previous = {"scenarios": [{"id": "brief_small", "traces": {"broken": "stale.json"}}]}
    (tmp_path / "manifest.json").write_text(json.dumps(previous))
    assert export_viz.main([
        "--only", "broken", "--inputs", str(ROOT / "inputs" / "brief_small.txt"),
        "--out", str(tmp_path),
    ]) == 1
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["scenarios"][0]["traces"] == {}


def test_native_trace_preserves_duplicate_zero_duration_call_ids():
    from dispatch.simulation import SimulationConfig, simulate
    from dispatch.trace import build_trace
    from tester.inputs import parse_input as parse_dispatch_input

    result = simulate(*parse_dispatch_input("1\n00:00 0 E 0\n00:00 0 E 0\n"),
                      SimulationConfig(staging=False))
    segments = build_trace(result, "duplicates")["vehicles"][0]["segments"]
    assert [segment["kind"] for segment in segments] == [
        "to_job", "on_job", "to_job", "on_job", "to_base",
    ]
    dispatched_ids = [segment["callId"] for segment in segments if segment["kind"] == "to_job"]
    serviced_ids = [segment["callId"] for segment in segments if segment["kind"] == "on_job"]
    assert sorted(dispatched_ids) == [0, 1]
    assert dispatched_ids == serviced_ids
