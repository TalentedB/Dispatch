DIRECTIONS = {"N": (0, 1), "S": (0, -1), "E": (1, 0), "W": (-1, 0)}


def parse_file(path):
    with open(path) as file:
        lines = [line.split() for line in file if line.strip()]

    vehicle_count = int(lines[0][0])
    calls = []

    for words in lines[1:]:
        hours, minutes = words[0].split(":")
        call_time = int(hours) * 60 + int(minutes)
        duration = int(words[-1])
        moves = words[1:-1]

        x, y = 0, 0
        for i in range(0, len(moves), 2):
            steps = int(moves[i])
            dx, dy = DIRECTIONS[moves[i + 1].upper()]
            x += dx * steps
            y += dy * steps

        calls.append((call_time, x, y, duration))

    calls.sort(key=lambda call: call[0])
    return vehicle_count, calls
