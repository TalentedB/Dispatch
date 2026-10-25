def format_time(minutes):
    days, minutes = divmod(minutes, 1440)
    text = f"{minutes // 60:02d}:{minutes % 60:02d}"
    if days:
        text += f"+{days}d"
    return text


def format_point(x, y):
    parts = []
    if y > 0:
        parts.append(f"{y}N")
    if y < 0:
        parts.append(f"{-y}S")
    if x > 0:
        parts.append(f"{x}E")
    if x < 0:
        parts.append(f"{-x}W")
    if not parts:
        return "base"
    return " ".join(parts)


def print_dispatch(vehicle, origin, call_time, x, y, leave_time, arrival_time):
    location = format_point(x, y)
    origin = format_point(origin[0], origin[1])
    response = arrival_time - call_time
    print(f"{format_time(call_time)}  {location:<9} vehicle {vehicle.id} from {origin:<9} "
          f"leaves {format_time(leave_time)}  arrives {format_time(arrival_time)}  ({response}m)")


def write_events(path, events):
    with open(path, "w") as file:
        for minute, vehicle_id, text in events:
            file.write(f"Vehicle {vehicle_id}: {format_time(minute)} {text}\n")


def grid_label(size):
    side = 2 * size
    return f"{side}x{side} blocks (up to {size} from base)"


def print_batch(minute, count):
    print(f"{format_time(minute)}  MILP batch of {count} calls")


def print_grid(minute, size):
    print(f"{format_time(minute)}  grid grows to {grid_label(size)}")


def print_summary(results, vehicle_count, end_time, size):
    if not results:
        print("\nNo calls.")
        return

    first_call = results[0][0]
    responses = [response for _, response, _, _ in results]
    travel = sum(travel for _, _, travel, _ in results)
    work = sum(duration for _, _, _, duration in results)

    print()
    print(f"Calls handled:        {len(results)} with {vehicle_count} vehicles")
    print(f"First call:           {format_time(first_call)}")
    print(f"All jobs finished:    {format_time(end_time)}")
    print(f"Full time required:   {end_time - first_call}m")
    print(f"Total response time:  {sum(responses)}m")
    print(f"Average response:     {sum(responses) / len(responses):.1f}m")
    print(f"Worst response:       {max(responses)}m")
    print(f"Total travel time:    {travel}m")
    print(f"Total on-scene time:  {work}m")
    print(f"Final grid:           {grid_label(size)}")
