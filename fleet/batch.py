import pulp


def solve_model(first, between, durations, waited, worst_cap=None):
    # first[v][i]: minutes until vehicle v could reach call i as its next job
    # between[i][j]: minutes to drive from call i to call j
    # waited[i]: minutes call i had already waited when this batch is solved
    vehicles = range(len(first))
    calls = range(len(durations))
    big = (max(max(row) for row in first) + sum(durations)
           + (len(durations) + 1) * max(max(row) for row in between) + 1) * 2

    problem = pulp.LpProblem("batch", pulp.LpMinimize)
    x = {(v, i): pulp.LpVariable(f"x_{v}_{i}", cat="Binary") for v in vehicles for i in calls}
    y = {(v, i, j): pulp.LpVariable(f"y_{v}_{i}_{j}", cat="Binary")
         for v in vehicles for i in calls for j in calls if i != j}
    arrive = {i: pulp.LpVariable(f"a_{i}", lowBound=0) for i in calls}
    worst = pulp.LpVariable("worst", lowBound=0)

    for i in calls:
        # Every call gets exactly one vehicle
        problem += pulp.lpSum(x[v, i] for v in vehicles) == 1
        problem += worst >= arrive[i] + waited[i]
        for v in vehicles:
            problem += arrive[i] >= first[v][i] - big * (1 - x[v, i])

    for (v, i, j), before in y.items():
        # If v does i before j, j can't be reached until i is done and v drives over
        problem += arrive[j] >= arrive[i] + durations[i] + between[i][j] - big * (1 - before)
        problem += before <= x[v, i]
        problem += before <= x[v, j]
        if i < j:
            problem += before + y[v, j, i] >= x[v, i] + x[v, j] - 1

    if worst_cap is None:
        problem += worst
    else:
        problem += worst <= worst_cap
        problem += pulp.lpSum(arrive[i] + waited[i] for i in calls)

    problem.solve(pulp.PULP_CBC_CMD(msg=False))
    if pulp.LpStatus[problem.status] != "Optimal":
        return None
    return worst.value(), x, y


def plan_batch(first, between, durations, waited):
    # Minimise the worst response first, then total response without making the worst any longer
    solved = solve_model(first, between, durations, waited)
    if solved:
        solved = solve_model(first, between, durations, waited, round(solved[0]))
    if not solved:
        return None

    _, x, y = solved
    plans = []
    for v in range(len(first)):
        taken = [i for i in range(len(durations)) if x[v, i].value() > 0.5]
        # Order by how many of its calls come before each one
        taken.sort(key=lambda i: sum(y[v, j, i].value() > 0.5 for j in range(len(durations)) if j != i))
        plans.append(taken)
    return plans
