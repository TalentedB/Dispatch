from pathlib import Path

import pytest

from tester.checker import check
from tester.inputs import BASE, InputError, Point, parse_input, read_input

INPUTS = Path(__file__).resolve().parent.parent / "inputs"
EXPECTED = sorted(INPUTS.glob("*.expected"))


def run_check(input_text: str, output: str):
    n, calls = parse_input(input_text)
    return check(n, calls, output)


def brief_2() -> tuple[str, list[str]]:
    return (INPUTS / "brief_2_vehicles.txt").read_text(), (INPUTS / "brief_2_vehicles.expected").read_text().splitlines()


def assert_invalid(result, fragment: str):
    assert not result.valid
    assert any(fragment in e for e in result.errors), result.errors


# --- input parsing ------------------------------------------------------------

def test_parses_brief_input():
    n, calls = parse_input("2\n10:45 15 N 20 W 45\n11:00 2 S 3 E 30\n16:02 4 E 15\n")
    assert n == 2
    assert [(c.time, c.location, c.duration) for c in calls] == [
        (645, Point(-20, 15), 45), (660, Point(3, -2), 30), (962, Point(4, 0), 15)]


@pytest.mark.parametrize("line, location", [
    ("09:00 3 S 10", Point(0, -3)),
    ("09:00 3s 10", Point(0, -3)),
    ("9:00 2 W 4 N 10", Point(-2, 4)),
    ("09:00 0 N 0 E 10", BASE),
])
def test_parses_input_variants(line, location):
    _, [call] = parse_input(f"1\n{line}\n")
    assert call.location == location


@pytest.mark.parametrize("text", ["", "two\n", "0\n", "1\n25:00 1 N 5\n", "1\n10:00 1 N\n",
                                  "1\n10:00 1 N 2 S 5\n", "1\n10:00 1 Q 5\n"])
def test_rejects_bad_input(text):
    with pytest.raises(InputError):
        parse_input(text)


def test_all_shipped_inputs_parse():
    for path in list(INPUTS.glob("*.txt")) + list((INPUTS / "generated").glob("*.txt")):
        read_input(str(path))


# --- known-good outputs pass ----------------------------------------------------

@pytest.mark.parametrize("expected", EXPECTED, ids=lambda p: p.stem)
def test_expected_outputs_are_valid(expected):
    n, calls = read_input(str(expected.with_suffix(".txt")))
    result = check(n, calls, expected.read_text())
    assert result.errors == []


def test_metrics_for_brief_2_vehicles():
    inp, out = brief_2()
    m = run_check(inp, "\n".join(out)).metrics
    assert m.calls_served == 3
    assert m.max_response == 35  # 10:45 call reached at 11:20
    assert m.avg_response == pytest.approx((35 + 5 + 4) / 3)
    assert m.avg_delay == 0
    assert m.total_drive == 88
    assert m.vehicles_used == 2


def test_partial_return_counts_toward_driving():
    m = run_check((INPUTS / "brief_small.txt").read_text(), (INPUTS / "brief_small.expected").read_text()).metrics
    assert m.total_drive == 5 + 1 + 2 + 6


REDIRECT_INPUT = "1\n12:00 2 N 3 E 1\n12:08 5 N 1 E 1\n"
REDIRECT_PREFIX = """\
Vehicle 0: 12:00 Start route to job
Vehicle 0: 12:00 Drive 2 minutes north and 3 minutes east
Vehicle 0: 12:05 Start job
Vehicle 0: 12:06 Finish job
Vehicle 0: 12:06 Start route to base
Vehicle 0: 12:06 Drive 2 minutes south and 3 minutes west
"""


def test_redirect_accepts_north_south_first():
    # After 2 min heading home N/S-first, the vehicle is at 3 E.
    out = REDIRECT_PREFIX + """\
Vehicle 0: 12:08 Start route to job
Vehicle 0: 12:08 Drive 5 minutes north and 2 minutes west
Vehicle 0: 12:15 Start job
Vehicle 0: 12:16 Finish job
Vehicle 0: 12:16 Start route to base
Vehicle 0: 12:16 Drive 5 minutes south and 1 minutes west
Vehicle 0: 12:22 Arrive at base
"""
    assert run_check(REDIRECT_INPUT, out).errors == []


def test_redirect_accepts_east_west_first():
    # After 2 min heading home E/W-first, the vehicle is at 2 N 1 E.
    out = REDIRECT_PREFIX + """\
Vehicle 0: 12:08 Start route to job
Vehicle 0: 12:08 Drive 3 minutes north
Vehicle 0: 12:11 Start job
Vehicle 0: 12:12 Finish job
Vehicle 0: 12:12 Start route to base
Vehicle 0: 12:12 Drive 5 minutes south and 1 minute west
Vehicle 0: 12:18 Arrive at base
"""
    assert run_check(REDIRECT_INPUT, out).errors == []


def test_job_at_base_with_no_drive_lines():
    out = """\
Vehicle 0: 09:00 Start route to job
Vehicle 0: 09:00 Start job
Vehicle 0: 09:10 Finish job
Vehicle 0: 09:10 Start route to base
Vehicle 0: 09:10 Arrive at base
"""
    assert run_check("1\n09:00 0 N 0 E 10\n", out).errors == []


def test_past_midnight():
    out = """\
Vehicle 0: 23:50 Start route to job
Vehicle 0: 23:50 Drive 10 minutes south and 10 minutes east
Vehicle 0: 00:10 Start job
Vehicle 0: 00:40 Finish job
Vehicle 0: 00:40 Start route to base
Vehicle 0: 00:40 Drive 10 minutes north and 10 minutes west
Vehicle 0: 01:00 Arrive at base
"""
    assert run_check("1\n23:50 10 S 10 E 30\n", out).errors == []


# --- broken outputs are caught --------------------------------------------------

def test_catches_wrong_job_duration():
    inp, out = brief_2()
    out[out.index("Vehicle 0: 16:21 Finish job")] = "Vehicle 0: 16:22 Finish job"
    assert_invalid(run_check(inp, "\n".join(out)), "15-min job")


def test_catches_wrong_drive_time():
    inp, out = brief_2()
    out[out.index("Vehicle 1: 11:05 Start job")] = "Vehicle 1: 11:04 Start job"
    assert_invalid(run_check(inp, "\n".join(out)), "the drive gets there at 11:05")


def test_catches_drive_to_nowhere():
    inp, out = brief_2()
    i = out.index("Vehicle 1: 11:00 Drive 2 minutes south and 3 minutes east")
    out[i] = "Vehicle 1: 11:00 Drive 2 minutes south and 2 minutes east"
    assert_invalid(run_check(inp, "\n".join(out)), "doesn't reach any open call")


def test_catches_unserved_call():
    inp, out = brief_2()
    out = [line for line in out if not line.startswith("Vehicle 1")]
    assert_invalid(run_check(inp, "\n".join(out)), "is never served")


def test_catches_leaving_before_call_arrives():
    out = """\
Vehicle 0: 10:59 Start route to job
Vehicle 0: 10:59 Drive 2 minutes south
Vehicle 0: 11:01 Start job
Vehicle 0: 11:02 Finish job
Vehicle 0: 11:02 Start route to base
Vehicle 0: 11:02 Drive 2 minutes north
Vehicle 0: 11:04 Arrive at base
"""
    assert_invalid(run_check("1\n11:00 2 S 1\n", out), "only comes in at 11:00")


def test_catches_switching_jobs():
    out = """\
Vehicle 0: 10:00 Start route to job
Vehicle 0: 10:00 Drive 10 minutes north
Vehicle 0: 10:01 Start route to job
"""
    assert_invalid(run_check("1\n10:00 10 N 5\n10:01 1 S 5\n", out), "can't switch jobs")


def test_catches_missing_return_to_base():
    inp, out = brief_2()
    assert_invalid(run_check(inp, "\n".join(out[:-3])), "never returns to base")


def test_catches_out_of_order_lines():
    inp, out = brief_2()
    i, j = out.index("Vehicle 1: 11:05 Start job"), out.index("Vehicle 0: 11:20 Start job")
    out[i], out[j] = out[j], out[i]
    assert_invalid(run_check(inp, "\n".join(out)), "time goes backwards")


def test_catches_unknown_vehicle_and_garbage():
    inp, out = brief_2()
    assert_invalid(run_check(inp, "\n".join(out + ["Vehicle 7: 17:00 Arrive at base"])), "doesn't exist")
    assert_invalid(run_check(inp, "\n".join(out + ["hello"])), "not in 'Vehicle N")
    assert_invalid(run_check(inp, "\n".join(out + ["Vehicle 0: 17:00 Teleport"])), "unknown action")


def test_catches_skipped_arrive_at_base():
    out = """\
Vehicle 0: 10:00 Start route to job
Vehicle 0: 10:00 Drive 1 minutes north
Vehicle 0: 10:01 Start job
Vehicle 0: 10:02 Finish job
Vehicle 0: 10:02 Start route to base
Vehicle 0: 10:02 Drive 1 minutes south
Vehicle 0: 10:30 Start route to job
"""
    assert_invalid(run_check("1\n10:00 1 N 1\n10:30 1 N 1\n", out), "should have printed 'Arrive at base'")
