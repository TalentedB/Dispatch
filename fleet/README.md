# Abdullah's fleet algorithm

The six Python source files in this directory are copied unchanged from
`TalentedB/UVec2026`, branch `abdullah`, commit `25b46f2`.

The active `pathfinding.solve` policy queues calls on the earliest-arriving
vehicle, and redistributes idle vehicles to posts across an expanding square.
It starts at minute zero, moves east/west before north/south, and stops when
the final job finishes. It does not force the fleet back to hospital.
For a single idle vehicle, the selected central post can be the hospital.

MILP batching in `batch.py` is disabled by comments in the original dispatcher.
The active algorithm needs only the standard library. PuLP is needed only if
the team chooses to enable and validate that separate experimental code.

`tools/abdullah_trace.py` adapts returned events to `uvec.trace/v1`, normalizes
vehicle IDs, retains standby movement and interruptions, and validates physical
continuity and call coverage. This uses native traces because the legacy text
checker requires returns to base and cannot express standby posts. The trace's
validation verdict comes from the adapter, not the legacy text checker.

Export with the other algorithms:

```sh
python tools/export_viz.py
```

Or produce one native trace for upload:

```sh
python -m tools.abdullah_trace inputs/brief_small.txt > abdullah.json
```

Comparison travel totals include standby travel from minute zero. The active
algorithm may therefore stage vehicles before the first call. Baselines wait
at base; this is a policy difference to consider when comparing results.
