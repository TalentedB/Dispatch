from pathlib import Path

import pytest

from tools.abdullah_trace import build_trace

ROOT = Path(__file__).resolve().parents[1]
INPUTS = sorted((ROOT / "inputs").rglob("*.txt"))


@pytest.mark.parametrize("path", INPUTS, ids=lambda p: p.stem)
def test_abdullah_trace_covers_every_call_with_continuous_movement(path):
    trace = build_trace(path.read_text(), path.stem)
    assert trace["check"]["valid"], trace["check"]["errors"]
    assert trace["metrics"]["calls_served"] == len(trace["calls"])
    assert [v["id"] for v in trace["vehicles"]] == list(range(trace["scenario"]["vehicles"]))
    for vehicle in trace["vehicles"]:
        for segment in vehicle["segments"]:
            if segment["kind"] == "on_job":
                call = trace["calls"][segment["callId"]]
                assert segment["end"] - segment["start"] == call["duration"]
                assert segment["path"] == [[call["x"], call["y"]]]


def test_redirected_post_starts_job_from_actual_position():
    trace = build_trace((ROOT / "inputs/brief_small.txt").read_text(), "small")
    segments = trace["vehicles"][0]["segments"]
    post = segments[2]
    assert post["kind"] == "reposition"
    assert post["interrupted"] and post["end"] == 728
    assert segments[3]["path"] == [[4, 0], [6, 0]]
    assert trace["metrics"]["avg_response"] == 3.5


def test_duplicate_zero_duration_calls_and_empty_input():
    trace = build_trace("1\n00:00 0\n00:00 0\n", "duplicates")
    assert trace["check"]["valid"], trace["check"]["errors"]
    assert sorted(s["callId"] for s in trace["vehicles"][0]["segments"]
                  if s["kind"] == "on_job") == [0, 1]
    empty = build_trace("2\n", "empty")
    assert empty["check"]["valid"]
    assert empty["metrics"]["calls_served"] == 0
