# Dispatch algorithms

We implemented four standard, well-known dispatch algorithms on a shared
simulation engine and compared them. None of them are new; each comes from
emergency-services, vehicle-routing, or ride-hailing practice.

## Shared engine (`solver/engine.py`)

The engine runs the day minute by minute and enforces the rules:

- Vehicles start at base (0, 0). Travel is Manhattan distance: 1 minute per block.
- A job a vehicle is driving to or working on is locked. It can't switch.
- A vehicle driving home can be redirected from wherever it is. It drives the
  north/south leg first, then east/west.
- A vehicle with nothing to do heads home.

Each minute is processed in a fixed order:

1. Finish jobs.
2. Give new calls to the algorithm.
3. Let the algorithm react to freed vehicles.
4. Send each free vehicle that has work to its next job.

The algorithm only decides which vehicle serves which call, and when.

## 1. Greedy earliest arrival (`greedy`)

Send each call to the vehicle that can **arrive soonest**, including busy
ones. A busy vehicle chains the job right after its current work. Ties go to
the lowest vehicle number.

- **Origin:** "closest unit" dispatch, extended to busy units. This matches
  every example in the brief.
- **Strength:** simple, and it chains jobs onto busy vehicles.
- **Weakness:** a job is committed the moment the call arrives, even if a
  better vehicle frees up later.

## 2. Closest idle vehicle, first-come-first-served (`closest_idle`)

Send the call to the **nearest free vehicle** by Manhattan distance. A free
vehicle is one sitting at base or driving home. If no vehicle is free, the
call waits in a central queue. When a vehicle frees up, it takes the
**oldest** waiting call.

- **Origin:** the standard ambulance dispatch rule. "In practice as well as in
  literature, it is commonly believed that the closest idle ambulance is the
  best choice" (Jagtenberg et al.).
- **Strength:** the most common real-world rule, and it is fair (oldest first).
- **Weakness:** it never chains a job onto a busy vehicle, even one that is
  nearly done right next door. Under load, freed vehicles cross the map to
  reach old calls.

## 3. Nearest neighbor (`nearest_neighbor`)

Same as closest idle, except that when a vehicle frees up, it takes the
**closest** waiting call instead of the oldest. When several vehicles and
calls are free at once, it repeatedly pairs the closest vehicle and call.

- **Origin:** the nearest-neighbor policy for the dynamic traveling repairman
  problem (Bertsimas & van Ryzin, 1991). It is the routing analogue of
  "shortest job first" in queueing.
- **Strength:** much less wasted driving under load, and the best average
  response time of the four.
- **Weakness:** a far-away call can keep getting skipped. Its worst response
  can be worse than greedy's.

## 4. Hungarian batch matching (`hungarian`)

Each time a call arrives or a vehicle frees up, solve the **assignment
problem**: match all free vehicles to waiting calls so that the total
Manhattan distance is as small as possible. If there are more calls than
vehicles, the leftover calls keep waiting. This uses the Kuhn–Munkres
(Hungarian) algorithm, O(n³).

- **Origin:** batch matching in ride-hailing dispatch. Requests and free
  drivers are collected and matched to minimize total pickup time.
- **Strength:** optimal for each batch. Nearest neighbor's "closest pair
  first" can be beaten: with vehicles at 0E and 3E and calls at 2E and 6E,
  nearest neighbor drives 1 + 6 = 7 blocks and Hungarian drives 2 + 3 = 5.
  This case is a unit test.
- **Weakness:** batches here are usually tiny (often one free vehicle), so it
  rarely differs from nearest neighbor. It has the same starvation risk.

## Results

`python3 tools/stress.py --n 200` ran 600 random scenarios, and the
independent checker validated every output.

| algorithm | light | medium | heavy | worst wait (light) | output same as greedy (light) |
|---|---|---|---|---|---|
| greedy | 34.3 | 133.0 | 291.4 | 559 | 100% |
| closest_idle | 34.6 (+1%) | 139.7 (+5%) | 302.3 (+4%) | 559 | 74% |
| **nearest_neighbor** | **29.0 (−16%)** | **98.5 (−26%)** | **209.2 (−28%)** | 800 | 62% |
| **hungarian** | **29.0 (−16%)** | **98.4 (−26%)** | **209.2 (−28%)** | 800 | 62% |

Light, medium and heavy are average response times in minutes; percentages
are compared with greedy. The first three columns also add up to total fleet
driving at heavy load: greedy 113k minutes, closest idle 129k, nearest
neighbor and Hungarian 67k.

What the results show:

- **Nearest neighbor and Hungarian win clearly** on average response, and they
  drive far less under load. They are almost identical because batches are
  usually one vehicle.
- **The trade-off is fairness.** Their worst single wait at light load is 800
  minutes, against greedy's 559. That is the known nearest-neighbor weakness:
  far calls get skipped.
- **Closest idle is the weakest here**, because it never chains onto a busy
  vehicle. Greedy's chaining is worth more than "only send free units".
- **Greedy is the safe choice if outputs are compared line by line**, because
  the brief's examples follow it exactly. All four algorithms reproduce all
  three examples.

## Sources

- Jagtenberg, Bhulai, van der Mei, *Dynamic ambulance dispatching: is the
  closest-idle policy always optimal?*:
  https://ideas.repec.org/a/kap/hcarem/v20y2017i4d10.1007_s10729-016-9368-0.html
  and https://ir.cwi.nl/pub/24632/
- Bertsimas & van Ryzin (1991), *A stochastic and dynamic vehicle routing
  problem in the Euclidean plane*:
  https://ideas.repec.org/a/inm/oropre/v39y1991i4p601-615.html
  (working paper: https://dspace.mit.edu/bitstream/1721.1/2353/1/SWP-3286-23735265.pdf)
- Ride-hailing batch matching with the Hungarian algorithm:
  https://www.resumelens.org/blog/system-design/designing-a-ride-sharing-matching-algorithm
  and https://repository.petra.ac.id/id/eprint/20274/
