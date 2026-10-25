from collections import deque
from itertools import permutations

# from .batch import plan_batch
from .models import Vehicle
from .report import format_point, print_batch, print_dispatch, print_grid, print_summary

# Smallest city is 4x4 blocks: 2 each way from base
MIN_GRID = 2


def distance(a, b):
    total = 0
    # X, Y, minutes until free
    for i in range(len(a)):
        total += abs(a[i] - b[i])
    return total


def step_toward(pos, target):
    # Move one intersection, east/west first, then north/south
    for i in range(2):
        if pos[i] != target[i]:
            pos[i] += 1 if target[i] > pos[i] else -1
            return


def plan_time(pos, jobs):
    # Minutes to drive to and finish every queued job, starting from pos
    total = 0
    at = pos[:2]
    for _, x, y, duration in jobs:
        total += distance(at, [x, y]) + duration
        at = [x, y]
    return total


def end_point(vehicle):
    # Where the vehicle will be, and how many minutes until it gets there and is free
    x, y = vehicle.pos[:2]
    if vehicle.jobs:
        x, y = vehicle.jobs[-1][1:3]
    return [x, y, vehicle.pos[2]]


def grow_grid(size, call):
    # Grid is a square around base, big enough for the furthest call so far
    _, x, y, _ = call
    return max(size, abs(x), abs(y))


def even_posts(count, x0, x1, y0, y1):
    # Split the area into equal rectangles, one per vehicle, cutting the longer side
    if count == 1:
        return [(round((x0 + x1) / 2), round((y0 + y1) / 2))]

    left = count // 2
    if x1 - x0 >= y1 - y0:
        cut = x0 + (x1 - x0) * left / count
        return even_posts(left, x0, cut, y0, y1) + even_posts(count - left, cut, x1, y0, y1)

    cut = y0 + (y1 - y0) * left / count
    return even_posts(left, x0, x1, y0, cut) + even_posts(count - left, x0, x1, cut, y1)


def start_route(minute, vehicle, events):
    # Log heading off to the next queued job, if it is somewhere else
    _, x, y, _ = vehicle.jobs[0]
    drive = distance(vehicle.pos[:2], [x, y])
    if drive:
        events.append((minute, vehicle.id, f"Start Route to Job {format_point(x, y)}"))
        events.append((minute, vehicle.id, f"Drive {drive} minutes"))


def redistribute(minute, idle, size, events):
    # Give each idle vehicle a post, keeping the longest drive to a post as short as possible
    posts = even_posts(len(idle), -size, size, -size, size)
    order = idle
    if len(idle) <= 7:
        order = min(permutations(idle), key=lambda order: (
            max(distance(v.pos[:2], p) for v, p in zip(order, posts)),
            sum(distance(v.pos[:2], p) for v, p in zip(order, posts)),
        ))
    for vehicle, post in zip(order, posts):
        if post != vehicle.post and list(post) != vehicle.pos[:2]:
            events.append((minute, vehicle.id, f"Start Route to Post {format_point(*post)}"))
            events.append((minute, vehicle.id, f"Drive {distance(vehicle.pos[:2], post)} minutes"))
        vehicle.post = post


def assign(minute, vehicle, call, results, events):
    call_time, x, y, duration = call
    target = [x, y, 0]
    origin = end_point(vehicle)
    leave_time = minute + origin[2]
    arrival_time = minute + distance(origin, target)
    print_dispatch(vehicle, origin, call_time, x, y, leave_time, arrival_time)
    travel = distance(origin[:2], target[:2])
    results.append((call_time, arrival_time - call_time, travel, duration))

    was_idle = not vehicle.jobs and vehicle.pos[2] == 0
    vehicle.jobs.append(call)
    vehicle.post = None
    vehicle.pos[2] += travel + duration
    if was_idle:
        start_route(minute, vehicle, events)


def dispatch(minute, queue, vehicles, results, events):
    # MILP for calls arriving together, disabled for now; every call is assigned greedily
    # if len(queue) > 1:
    #     starts = [end_point(vehicle) for vehicle in vehicles]
    #     first = [[distance(start, [x, y, 0]) for _, x, y, _ in queue] for start in starts]
    #     between = [[distance(a[1:3], b[1:3]) for b in queue] for a in queue]
    #     durations = [call[3] for call in queue]
    #     waited = [minute - call[0] for call in queue]
    #     plans = plan_batch(first, between, durations, waited)
    #     if plans:
    #         print_batch(minute, len(queue))
    #         for vehicle, taken in zip(vehicles, plans):
    #             for i in taken:
    #                 assign(minute, vehicle, queue[i], results, events)
    #         queue.clear()
    #         return

    for call in list(queue):
        target = [call[1], call[2], 0]
        best = min(vehicles, key=lambda vehicle: distance(end_point(vehicle), target))
        assign(minute, best, call, results, events)
        queue.remove(call)


def tick(minute, vehicle, events):
    # Arrive once the work here is done and the next job is at this spot
    while (vehicle.jobs and vehicle.pos[2] == plan_time(vehicle.pos, vehicle.jobs)
           and vehicle.pos[:2] == list(vehicle.jobs[0][1:3])):
        job = vehicle.jobs.pop(0)
        events.append((minute, vehicle.id, f"Arrive at Job {format_point(job[1], job[2])}"))
        events.append((minute, vehicle.id, "Start Job"))
        if job[3] == 0:
            events.append((minute, vehicle.id, "Finish Job"))
            if vehicle.jobs:
                start_route(minute, vehicle, events)

    # Idle, so drive toward its post for coverage
    if vehicle.pos[2] == 0:
        if not vehicle.jobs and vehicle.post and list(vehicle.post) != vehicle.pos[:2]:
            step_toward(vehicle.pos, vehicle.post)
            if list(vehicle.post) == vehicle.pos[:2]:
                events.append((minute + 1, vehicle.id, f"Arrive at Post {format_point(*vehicle.post)}"))
        return

    # No work left here, so drive to the next job
    working = vehicle.pos[2] > plan_time(vehicle.pos, vehicle.jobs)
    if not working:
        step_toward(vehicle.pos, vehicle.jobs[0][1:3])
    vehicle.pos[2] -= 1

    if working and vehicle.pos[2] == plan_time(vehicle.pos, vehicle.jobs):
        events.append((minute + 1, vehicle.id, "Finish Job"))
        if vehicle.jobs:
            start_route(minute + 1, vehicle, events)


def solve(vehicle_count, calls):
    vehicles = []
    for i in range(vehicle_count):
        vehicles.append(Vehicle(i + 1, [0, 0, 0]))

    incoming = deque(calls)
    queue = []
    results = []
    events = []
    size = MIN_GRID
    layout = None
    minute = 0

    # One tick per minute; runs past midnight until every job is finished
    while incoming or queue or any(vehicle.jobs or vehicle.pos[2] for vehicle in vehicles):
        while incoming and incoming[0][0] <= minute:
            call = incoming.popleft()
            queue.append(call)
            if grow_grid(size, call) > size:
                size = grow_grid(size, call)
                print_grid(minute, size)

        dispatch(minute, queue, vehicles, results, events)

        # Re-spread idle vehicles whenever who is idle or the grid size changes
        idle = [vehicle for vehicle in vehicles if not vehicle.jobs and vehicle.pos[2] == 0]
        if idle and (tuple(vehicle.id for vehicle in idle), size) != layout:
            redistribute(minute, idle, size, events)
            layout = (tuple(vehicle.id for vehicle in idle), size)

        for vehicle in vehicles:
            tick(minute, vehicle, events)

        minute += 1

    print_summary(results, vehicle_count, minute, size)
    return events
