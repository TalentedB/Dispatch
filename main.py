import sys

from fleet import parse_file, solve
from fleet.report import write_events

path = "input.txt"
if len(sys.argv) > 1:
    path = sys.argv[1]

vehicle_count, calls = parse_file(path)
events = solve(vehicle_count, calls)
write_events("output.txt", events)
