# Test inputs

- `*.txt` — input files in the brief's format.
- `*.expected` — the correct output for that input, when we know it. The benchmark
  checks each algorithm's output against these.
- `generated/` — random scenarios from `tools/generate_inputs.py` (no expected output;
  scored by metrics only).

## Fixes to the brief's printed examples

The brief's example outputs contain two arithmetic slips. Our `.expected` files
use the corrected times:

- `brief_2_vehicles`: the brief prints the 16:02 job finishing at 16:31, but the job
  takes 15 minutes, so it finishes at 16:21 (return to base at 16:25).
- `brief_1_vehicle`: the brief prints the first job starting at 11:00, but the drive is
  15 + 20 = 35 minutes, so it starts at 11:20. Every later time shifts by 20 minutes.
