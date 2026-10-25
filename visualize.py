import io
import json
import sys
import webbrowser
from contextlib import redirect_stdout
from pathlib import Path

from fleet import parse_file, pathfinding, report, solve

path = "input.txt"
if len(sys.argv) > 1:
    path = sys.argv[1]

vehicle_count, calls = parse_file(path)
call_index = {call: i for i, call in enumerate(calls)}
frames = []
grid = {"size": pathfinding.MIN_GRID, "log": []}

# Record a frame each minute by wrapping dispatch and print_grid; the algorithm itself is untouched
original_dispatch = pathfinding.dispatch
original_print_grid = pathfinding.print_grid


def recording_print_grid(minute, size):
    original_print_grid(minute, size)
    grid["size"] = size
    grid["log"].append(f"{report.format_time(minute)}  grid grows to {report.grid_label(size)}")


def recording_dispatch(minute, queue, vehicles, results, events):
    log = io.StringIO()
    with redirect_stdout(log):
        original_dispatch(minute, queue, vehicles, results, events)
    frames.append({
        "minute": minute,
        "grid": grid["size"],
        "queue": [call_index[call] for call in queue],
        "vehicles": [
            {"id": v.id, "pos": list(v.pos), "jobs": [call_index[job] for job in v.jobs], "post": v.post}
            for v in vehicles
        ],
        "log": grid["log"] + log.getvalue().splitlines(),
    })
    grid["log"] = []


pathfinding.dispatch = recording_dispatch
pathfinding.print_grid = recording_print_grid
output = io.StringIO()
with redirect_stdout(output):
    solve(vehicle_count, calls)
pathfinding.dispatch = original_dispatch
pathfinding.print_grid = original_print_grid

summary = output.getvalue().split("\n\n", 1)[-1].strip()
data = {
    "calls": [list(call) for call in calls],
    "frames": frames,
    "summary": summary,
}

template = (Path(__file__).parent / "visualize_template.html").read_text()
out = Path(__file__).parent / "visualize.html"
out.write_text(template.replace("__DATA__", json.dumps(data)))
print(summary)
print(f"\nWrote {out}")
webbrowser.open(out.as_uri())
