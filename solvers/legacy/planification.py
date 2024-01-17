"""
Solves operation planification problem using MILP solver.
"""
import colorsys
import datetime
import json
import logging
import time

import numpy as np
import pandas as pd
import plotly.express as px
from django.db.models.query import QuerySet
from minizinc import Instance, Model, Solver
from z3 import Optimize, Int, Real, If, Implies, Or, And, sat, unsat, set_param, Sum

from db.dao.workstation import get_all_product_stations, get_all_stations
from db.models_uvt import Operation, Operationworkstation

logging.basicConfig(level=logging.WARNING)
set_param('parallel.enable', True)
set_param('parallel.threads.max', 12)


def get_all_operations() -> QuerySet[Operation]:
    """
    Get all operations from database.
    """
    return Operation.objects.all().using("scampml_uvt")


def get_all_operation_workstations() -> QuerySet[Operationworkstation]:
    """
    Get all operation workstations from database.
    """
    return Operationworkstation.objects.all().using("scampml_uvt")


def get_planification_problem():
    """
    Parse DB and returns planification problem as dictionary.
    """
    operations = get_all_operations().order_by('id').filter(
        purchaseorderrowid=2000)  # Temporary ignore letsa example operations
    operation_properties = ['id', 'productcode', 'quantity', 'parentoperationid']
    operation_list_of_tuples = list(operations.values_list(*operation_properties))

    operation_properties_list = list(map(list, list(zip(*operation_list_of_tuples))))

    planification_problem = {}
    planification_problem['operationIDs'] = operation_properties_list[operation_properties.index('id')]
    n = len(planification_problem['operationIDs'])
    planification_problem['n'] = n
    planification_problem['operationProductCode'] = operation_properties_list[operation_properties.index('productcode')]
    planification_problem['operationProductQuantity'] = operation_properties_list[
        operation_properties.index('quantity')]
    planification_problem['operationSuccessor'] = [-1 if x is None else planification_problem['operationIDs']
                                                                        .index(x) + 1 for x in
                                                   operation_properties_list[
                                                       operation_properties.index('parentoperationid')]]

    product_stations = get_all_product_stations().filter(
        productid__in=list(operations.order_by('productid').values_list('productid', flat=True).distinct()))
    planification_problem['workstationIDs'] = list(
        product_stations.order_by('stationid').values_list('stationid', flat=True).distinct())
    planification_problem['workstationNames'] = list(
        get_all_stations().filter(id__in=planification_problem['workstationIDs']).order_by('id').values_list('name',
                                                                                                             flat=True))
    m = len(planification_problem['workstationIDs'])
    planification_problem['m'] = m
    planification_problem['workstationAssignment'] = np.zeros((n, m), dtype=np.int8).tolist()
    planification_problem['assemblyTime'] = np.zeros((n, m)).tolist()
    planification_problem['unitAssemblyTime'] = np.zeros((n, m)).tolist()
    planification_problem['setupTime'] = np.zeros((n, m)).tolist()
    for operation in operations:
        for product_station in product_stations.filter(productid=operation.productid):
            planification_problem['workstationAssignment'][planification_problem['operationIDs'].index(operation.id)][
                planification_problem['workstationIDs'].index(product_station.stationid.id)] = 1
            planification_problem['assemblyTime'][planification_problem['operationIDs'].index(operation.id)][
                planification_problem['workstationIDs'].index(
                    product_station.stationid.id)] = float(operation.quantity * (
                        product_station.cycletime * product_station.estimatedoee) + product_station.setuptime)
            planification_problem['unitAssemblyTime'][planification_problem['operationIDs'].index(operation.id)][
                planification_problem['workstationIDs'].index(
                    product_station.stationid.id)] = float(product_station.cycletime * product_station.estimatedoee)
            planification_problem['setupTime'][planification_problem['operationIDs'].index(operation.id)][
                planification_problem['workstationIDs'].index(
                    product_station.stationid.id)] = float(product_station.setuptime)

    '''
    operation_workstations = get_all_operation_workstations()
    planification_problem['workstationIDs'] = list(operation_workstations.order_by('stationid').values_list('stationid', flat=True).distinct())
    m = len(planification_problem['workstationIDs'])
    planification_problem['m'] = m
    planification_problem['workstationAssignment'] = np.zeros((m, n), dtype=np.int8).tolist()
    planification_problem['assemblyTime'] = np.zeros((m, n)).tolist()
    for operation_id in planification_problem['operationIDs']:
        for operation_ws in operation_workstations.filter(operationid=operation_id):
            planification_problem['workstationAssignment'][planification_problem['workstationIDs'].index(operation_ws.stationid)][planification_problem['operationIDs'].index(operation_id)] = 1
            planification_problem['assemblyTime'][planification_problem['workstationIDs'].index(
                operation_ws.stationid)][planification_problem['operationIDs'].index(operation_id)] = float(operation_ws.productassemtime)
    '''

    planification_problem['finalOperationIDs'] = list(
        operations.filter(parentoperationid=None).values_list('id', flat=True).distinct())
    planification_problem['finalOperationPosition'] = [planification_problem['operationIDs'].index(x) + 1 for x in
                                                       planification_problem['finalOperationIDs']]
    planification_problem['finalOperations'] = len(planification_problem['finalOperationIDs'])
    planification_problem['finalDeadline'] = [0] * planification_problem['finalOperations']

    # current_time = datetime.datetime.now()
    current_time = datetime.datetime(2022, 5, 1)
    planification_problem['planificationStartTime'] = current_time.strftime('%Y-%m-%d %H:%M:%S.%f')

    for final_operation in operations.filter(id__in=planification_problem['finalOperationIDs']):
        planification_problem['finalDeadline'][planification_problem['finalOperationIDs'].index(final_operation.id)] = (
                    final_operation.deliverydate - current_time).total_seconds()
    planification_problem['M'] = int(max(planification_problem['finalDeadline']) * 2)

    with open('../solvers/planification_problem.json', 'w', encoding="utf8") as json_file:
        json.dump(planification_problem, json_file, indent=4, default=str)
    return planification_problem


def solve_planification_LS(planification_problem, solver="cplex", threads=1, timeout=60):
    """
    Solve planification Lot Sizing problem using MILP solver.
    """
    start_time = time.time()
    model = Model("../solvers/lot_sizing_v2.mzn")
    solverObj = Solver.lookup(solver)
    instance = Instance(solverObj, model)

    instance["n"] = planification_problem['n']
    instance["m"] = planification_problem['m']
    instance["W"] = planification_problem['workstationAssignment']
    instance["t"] = planification_problem['assemblyTime']
    instance["d"] = planification_problem['operationSuccessor']
    instance["E"] = planification_problem['finalOperations']
    instance["finalPosition"] = planification_problem['finalOperationPosition']
    instance["D"] = planification_problem['finalDeadline']
    instance["M"] = planification_problem['M']

    result = instance.solve(timeout=datetime.timedelta(seconds=timeout), processes=threads,
                            intermediate_solutions=False)
    print(f"Lot Sizing CPLEX {round(time.time() - start_time, 3)}s..")
    planification_solution = {}
    planification_solution["ExecutionTime"] = round(time.time() - start_time, 3)
    if result:
        planification_solution["Status"] = str(result.status)
        planification_solution["Objective"] = np.round(result["objective"])
        if result.status is result.status.SATISFIED or result.status is result.status.OPTIMAL_SOLUTION:
            for key in ["n", "operationIDs", "operationProductCode", "operationProductQuantity", "m", "workstationIDs",
                        "workstationNames", "planificationStartTime"]:
                planification_solution[key] = planification_problem[key]
            planification_solution["startTime"] = result["S"]
            planification_solution["completeTime"] = result["C"]
            n, m = planification_problem['n'], planification_problem['m']
            workstation_assignment = [0] * n
            for workstation in range(m):
                for operation in range(n):
                    if result["A"][operation][workstation] == 1:
                        workstation_assignment[operation] = planification_problem["workstationIDs"][workstation]
            planification_solution['workstationAssignment'] = workstation_assignment
    else:
        planification_solution["Status"] = "None"
        planification_solution["Objective"] = -1

    return planification_solution


def solve_planification_LS_z3(planification_problem, timeout=60):
    """
    Solve planification Lot Sizing problem using the Z3 SMT solver.
    """
    start_time = time.time()
    n = planification_problem['n']
    m = planification_problem['m']

    opt = Optimize()
    W = [[Int("W_%s_%s" % (i + 1, w + 1)) for w in range(m)] for i in range(n)]
    constraint_W = [W[i][w] == planification_problem['workstationAssignment'][i][w] for w in range(m) for i in range(n)]
    opt.add(constraint_W)

    t = [[Real("t_%s_%s" % (i + 1, w + 1)) for w in range(m)] for i in range(n)]
    constraint_t = [t[i][w] == planification_problem['assemblyTime'][i][w] for w in range(m) for i in range(n)]
    opt.add(constraint_t)

    M = Int('M')
    opt.add(M == planification_problem['M'])

    S = [Real("S_%s" % (i + 1)) for i in range(n)]
    C = [Real("C_%s" % (i + 1)) for i in range(n)]
    d = [Int("d_%s" % (i + 1)) for i in range(n)]
    constraint_d = [d[i] == planification_problem['operationSuccessor'][i] for i in range(n)]
    opt.add(constraint_d)

    A = [[Int("A_%s_%s" % (i + 1, w + 1)) for w in range(m)] for i in range(n)]
    constraint_A = [Or(A[i][w] == 0, A[i][w] == 1, ) for w in range(m) for i in range(n)]
    opt.add(constraint_A)

    delta = [[Real("delta_%s_%s" % (i + 1, j + 1)) for j in range(n)] for i in range(n)]
    constraint_delta = [Or(delta[i][j] == 0, delta[i][j] == 1, ) for j in range(n) for i in range(n)]
    opt.add(constraint_delta)

    E = planification_problem['finalOperations']
    finalPosition = [Int("finalPosition_%s" % (e + 1)) for e in range(E)]
    constraint_finalPosition = [finalPosition[e] == planification_problem['finalOperationPosition'][e] for e in
                                range(E)]
    opt.add(constraint_finalPosition)

    D = [Real("D_%s" % (e + 1)) for e in range(E)]
    constraint_D = [D[e] == planification_problem['finalDeadline'][e] for e in range(E)]
    opt.add(constraint_D)

    constraint_1 = [Sum([A[i][w] for w in range(m)]) == 1 for i in
                    range(n)]  # each task is assigned to exactly one workstation
    constraint_2 = [Sum([If(W[i][w] == 0, A[i][w], 0) for w in range(m) for i in
                         range(n)]) == 0]  # the task cannot be assigned to non-eligible workstations
    constraint_3 = [Implies(A[i][w] == 1, C[i] == S[i] + t[i][w]) for w in range(m) for i in range(n)]
    constraint_4 = [S[i] >= 0 for i in range(n)]
    constraint_5 = [Implies(And(i != j, d[i] == j + 1), S[j] >= C[i]) for j in range(n) for i in range(n)]
    constraint_6 = [Implies(And(i != j, A[i][w] == 1, A[j][w] == 1),
                            And(delta[i][j] + delta[j][i] == 1, S[i] - C[j] >= M * (delta[i][j] - 1))) for w in range(m)
                    for j in range(n) for i in
                    range(n)]  # delta[i,j] = 1 if operation j precedes i (i,j ∈ K,i ̸= j,1≤K≤m), 0 otherwise.
    constraint_7 = [Implies(finalPosition[e] == i + 1, C[i] <= D[e]) for e in range(E) for i in range(n)]

    opt.add(constraint_1)
    opt.add(constraint_2)
    opt.add(constraint_3)
    opt.add(constraint_4)
    opt.add(constraint_5)
    opt.add(constraint_6)
    opt.add(constraint_7)

    def z3_min(vs):
        min_var = vs[0]
        for v in vs[1:]:
            min_var = If(v < min_var, v, min_var)
        return min_var

    def z3_max(vs):
        max_var = vs[0]
        for v in vs[1:]:
            max_var = If(v > max_var, v, max_var)
        return max_var

    objective = Real('objective')
    # opt.add(objective == sum([S[i] for i in range(n)]))
    # opt.add(objective == z3_min([S[i] for i in range(n)]))
    opt.add(objective == z3_max([If(finalPosition[e] == i + 1, C[i], 0) for e in range(E) for i in range(n)]))
    # h = opt.maximize(objective)
    h = opt.minimize(objective)
    run = 0
    max_runs = 100
    status = unsat
    timeleft = timeout * 1000
    opt.set("timeout", timeleft)
    z3_time = time.time()
    while run < max_runs and opt.check() == sat:
        status = sat
        # print(run, timeleft, eval(str(opt.model()[objective])))
        tmp_obj = opt.model()[objective]
        solution_model = opt.model()
        opt.add(objective < 0.99 * tmp_obj)
        opt.minimize(objective)
        run += 1

        timeleft -= (time.time() - z3_time) * 1000
        z3_time = time.time()
        opt.set("timeout", int(timeleft))

    print(f"Lot Sizing Z3 {round(time.time() - start_time, 3)}s..")
    planification_solution = {}
    planification_solution["ExecutionTime"] = round(time.time() - start_time, 3)
    planification_solution["Status"] = str(status)
    if status == sat:
        planification_solution["Objective"] = eval(str(solution_model[objective]))
        for key in ["n", "operationIDs", "operationProductCode", "operationProductQuantity", "m", "workstationIDs",
                    "workstationNames", "planificationStartTime"]:
            planification_solution[key] = planification_problem[key]
        planification_solution["startTime"] = [eval(str(solution_model[S[i]])) for i in range(n)]
        planification_solution["completeTime"] = [eval(str(solution_model[C[i]])) for i in range(n)]
        workstation_assignment = [0] * n
        for workstation in range(m):
            for operation in range(n):
                if solution_model[A[operation][workstation]] == 1:
                    workstation_assignment[operation] = planification_problem["workstationIDs"][workstation]
        planification_solution['workstationAssignment'] = workstation_assignment
    else:
        planification_solution["Objective"] = -1

    return planification_solution


def solve_planification_BS(planification_problem, solver="cplex", threads=1, timeout=60):
    """
    Solve planification Batch Splitting problem using MILP solver.
    """
    start_time = time.time()
    model = Model("../solvers/batch_splitting.mzn")
    solverObj = Solver.lookup(solver)
    instance = Instance(solverObj, model)

    instance["n"] = planification_problem['n']
    instance["W"] = planification_problem['m']
    instance["I"] = planification_problem['workstationAssignment']

    instance["t"] = planification_problem['unitAssemblyTime']
    instance["K"] = planification_problem['setupTime']
    instance["b"] = planification_problem['operationProductQuantity']

    instance["s"] = planification_problem['operationSuccessor']
    instance["E"] = planification_problem['finalOperations']
    instance["finalPosition"] = planification_problem['finalOperationPosition']
    instance["D"] = planification_problem['finalDeadline']
    instance["M"] = planification_problem['M']
    instance["movesize"] = 3

    result = instance.solve(timeout=datetime.timedelta(seconds=timeout), processes=threads,
                            intermediate_solutions=False)

    print(f"Batch Splitting CPLEX {round(time.time() - start_time, 3)}s..")
    planification_solution = {}
    planification_solution["ExecutionTime"] = round(time.time() - start_time, 3)
    if result:
        planification_solution["Status"] = str(result.status)
        planification_solution["Objective"] = np.round(result["objective"])
        if result.status is result.status.SATISFIED or result.status is result.status.OPTIMAL_SOLUTION:
            for key in ["n", "operationIDs", "operationProductCode", "operationProductQuantity", "m", "workstationIDs",
                        "workstationNames", "planificationStartTime"]:
                planification_solution[key] = planification_problem[key]
            planification_solution["startTime"] = result["S"]
            planification_solution["completeTime"] = result["F"]
            planification_solution['workstationAssignment'] = result["A"]
            planification_solution['Batch'] = result["B"]
    else:
        planification_solution["Status"] = "None"
        planification_solution["Objective"] = -1

    return planification_solution


def solve_planification_BS_z3(planification_problem, timeout=60):
    """
    Solve planification Batch Splitting problem using the Z3 SMT solver.
    """
    start_time = time.time()
    n = planification_problem['n']
    W = planification_problem['m']

    opt = Optimize()
    I = [[Int("I_%s_%s" % (i + 1, Y + 1)) for Y in range(W)] for i in range(n)]
    constraint_I = [I[i][Y] == planification_problem['workstationAssignment'][i][Y] for Y in range(W) for i in range(n)]
    opt.add(constraint_I)

    t = [[Real("t_%s_%s" % (i + 1, Y + 1)) for Y in range(W)] for i in range(n)]
    constraint_t = [t[i][Y] == planification_problem['unitAssemblyTime'][i][Y] for Y in range(W) for i in range(n)]
    opt.add(constraint_t)

    K = [[Real("K_%s_%s" % (i + 1, Y + 1)) for Y in range(W)] for i in range(n)]
    constraint_K = [K[i][Y] == planification_problem['setupTime'][i][Y] for Y in range(W) for i in range(n)]
    opt.add(constraint_K)

    b = [Int("b_%s" % (i + 1)) for i in range(n)]
    constraint_b = [b[i] == planification_problem['operationProductQuantity'][i] for i in range(n)]
    opt.add(constraint_b)

    movesize = Int('movesize')
    opt.add(movesize == 3)
    M = Int('M')
    opt.add(M == planification_problem['M'])

    S = [[Real("S_%s_%s" % (i + 1, Y + 1)) for Y in range(W)] for i in range(n)]
    F = [[Real("F_%s_%s" % (i + 1, Y + 1)) for Y in range(W)] for i in range(n)]
    B = [[Int("B_%s_%s" % (i + 1, Y + 1)) for Y in range(W)] for i in range(n)]
    s = [Int("s_%s" % (i + 1)) for i in range(n)]
    constraint_s = [s[i] == planification_problem['operationSuccessor'][i] for i in range(n)]
    opt.add(constraint_s)

    A = [[Int("A_%s_%s" % (i + 1, Y + 1)) for Y in range(W)] for i in range(n)]
    constraint_A = [Or(A[i][Y] == 0, A[i][Y] == 1, ) for Y in range(W) for i in range(n)]
    opt.add(constraint_A)

    delta = [[Real("delta_%s_%s" % (i + 1, j + 1)) for j in range(n)] for i in range(n)]
    constraint_delta = [Or(delta[i][j] == 0, delta[i][j] == 1, ) for j in range(n) for i in range(n)]
    opt.add(constraint_delta)

    E = planification_problem['finalOperations']
    finalPosition = [Int("finalPosition_%s" % (z + 1)) for z in range(E)]
    constraint_finalPosition = [finalPosition[z] == planification_problem['finalOperationPosition'][z] for z in
                                range(E)]
    opt.add(constraint_finalPosition)

    D = [Real("D_%s" % (z + 1)) for z in range(E)]
    constraint_D = [D[z] == planification_problem['finalDeadline'][z] for z in range(E)]
    opt.add(constraint_D)

    constraint_1 = [Sum([If(I[i][Y] == 0, A[i][Y], 0) for Y in range(W) for i in
                         range(n)]) == 0]  # the task cannot be assigned to non-eligible workstations
    constraint_2 = [Implies(And(Y1 != Y2, s[i] == j + 1, A[i][Y1] == 1, A[j][Y2] == 1),
                            S[j][Y2] >= S[i][Y1] + K[i][Y1] - K[j][Y2] + movesize * Sum([A[i][y] for y in range(W)]) *
                            t[i][Y1]) for Y1 in range(W)
                    for Y2 in range(W) for j in range(n) for i in range(n)]

    constraint_3 = [Implies(And(Y1 != Y2, s[i] == j + 1, A[i][Y1] == 1, A[j][Y2] == 1),
                            F[j][Y2] >= F[i][Y1] + + movesize * t[j][Y2]) for Y1 in range(W)
                    for Y2 in range(W) for j in range(n) for i in range(n)]

    constraint_3b = [Implies(And(s[i] == j + 1, A[i][Y1] == 1, A[j][Y2] == 1), S[j][Y2] >= F[i][Y1]) for Y1 in range(W)
                     for Y2 in range(W) for j in range(n) for i in range(n)]

    constraint_4 = [S[i][Y] >= 0 for Y in range(W) for i in range(n)]
    constraint_5 = [Implies(And(i != j, A[i][Y] == 1, A[j][Y] == 1),
                            And(delta[i][j] + delta[j][i] == 1, S[i][Y] >= F[j][Y] + M * (delta[j][i] - 1))) for Y in
                    range(W)
                    for j in range(n) for i in range(n)]

    constraint_6 = [Implies(A[i][Y] == 1, And(B[i][Y] > 0, F[i][Y] == S[i][Y] + K[i][Y] + B[i][Y] * t[i][Y])) for Y in
                    range(W) for i in range(n)]
    constraint_7 = [Sum([B[i][Y] for Y in range(W)]) == b[i] for i in range(n)]
    constraint_8 = [Implies(A[i][Y] == 0, And(B[i][Y] == 0, S[i][Y] == 0, F[i][Y] == 0)) for Y in range(W) for i in
                    range(n)]

    constraint_9 = [Implies(And(finalPosition[z] == i + 1, A[i][Y] == 1), F[i][Y] <= D[z]) for Y in range(W) for i in
                    range(n) for z in range(E)]

    opt.add(constraint_1)
    # opt.add(constraint_2)
    # opt.add(constraint_3)
    opt.add(constraint_3b)
    opt.add(constraint_4)
    opt.add(constraint_5)
    opt.add(constraint_6)
    opt.add(constraint_7)
    opt.add(constraint_8)
    opt.add(constraint_9)

    def z3_min(vs):
        min_var = vs[0]
        for v in vs[1:]:
            min_var = If(v < min_var, v, min_var)
        return min_var

    def z3_max(vs):
        max_var = vs[0]
        for v in vs[1:]:
            max_var = If(v > max_var, v, max_var)
        return max_var

    objective = Real('objective')
    # opt.add(objective == sum([S[i][Y] for Y in range(W) for i in range(n)]))
    opt.add(objective == z3_max(
        [If(And(finalPosition[z] == i + 1, A[i][Y] == 1), F[i][Y], 0) for Y in range(W) for i in range(n) for z in
         range(E)]))
    # opt.add(objective == z3_max([F[i][Y] for Y in range(W) for i in range(n)]))

    # h = opt.maximize(objective)
    h = opt.minimize(objective)

    run = 0
    max_runs = 100
    status = unsat
    timeleft = timeout * 1000
    opt.set("timeout", timeleft)
    print(f"Batch Splitting Z3 {round(time.time() - start_time, 3)}s..")
    z3_time = time.time()
    while run < max_runs and opt.check() == sat:
        status = sat
        # print(run, timeleft, eval(str(opt.model()[objective])))
        tmp_obj = opt.model()[objective]
        solution_model = opt.model()
        opt.add(objective < 0.99 * tmp_obj)
        opt.minimize(objective)
        run += 1

        timeleft -= (time.time() - z3_time) * 1000
        z3_time = time.time()
        opt.set("timeout", int(timeleft))

    planification_solution = {}
    print(f"Batch Splitting Z3 {round(time.time() - start_time, 3)}s..")
    planification_solution["ExecutionTime"] = round(time.time() - start_time, 3)
    planification_solution["Status"] = str(status)
    if status == sat:
        planification_solution["Objective"] = eval(str(solution_model[objective]))
        for key in ["n", "operationIDs", "operationProductCode", "operationProductQuantity", "m", "workstationIDs",
                    "workstationNames", "planificationStartTime"]:
            planification_solution[key] = planification_problem[key]
        planification_solution["startTime"] = [[eval(str(solution_model[S[i][Y]])) for Y in range(W)] for i in range(n)]
        planification_solution["completeTime"] = [[eval(str(solution_model[F[i][Y]])) for Y in range(W)] for i in
                                                  range(n)]
        planification_solution["Batch"] = [[eval(str(solution_model[B[i][Y]])) for Y in range(W)] for i in range(n)]
        planification_solution["workstationAssignment"] = [[eval(str(solution_model[A[i][Y]])) for Y in range(W)] for i
                                                           in range(n)]
    else:
        planification_solution["Objective"] = -1

    return planification_solution


def get_color_palette(n=5):
    """
    Return n-length color palette as hex string list.
    """
    hsv_tuples = [(x * 1.0 / n, 0.7, 0.9) for x in range(n)]
    hex_out = []
    for rgb in hsv_tuples:
        rgb = map(lambda x: int(x * 255), colorsys.hsv_to_rgb(*rgb))
        hex_out.append('#%02x%02x%02x' % tuple(rgb))
    return hex_out


def visualize_planification_LS(planification_solution, filename, title):
    """
    Create plotly gantt chart from solver Lot Sizing planification solution.
    """
    n = planification_solution['n']
    start_time = datetime.datetime.strptime(planification_solution['planificationStartTime'], '%Y-%m-%d %H:%M:%S.%f')

    data = []
    for i in range(n):
        ws = planification_solution["workstationIDs"].index(planification_solution["workstationAssignment"][i])
        data.append(dict(Start=(start_time + datetime.timedelta(seconds=planification_solution['startTime'][i])),
                         Finish=(start_time + datetime.timedelta(
                             seconds=planification_solution['completeTime'][i])),
                         Workstation=planification_solution["workstationNames"][ws],
                         ProductCode=planification_solution["operationProductCode"][i],
                         Q=planification_solution["operationProductQuantity"][i]))

    df = pd.DataFrame(data)
    fig = px.timeline(
        df,
        x_start="Start",
        x_end="Finish",
        y="Workstation",
        color="ProductCode",
        text="ProductCode",
        hover_data=["Q"],
    )
    fig.write_html(f"../db/templates/solvers/planification_{filename}.html", include_plotlyjs=True)
    with open('../solvers/solution_template.html', 'r', encoding="utf8") as template_file, open(
            f"../db/templates/solvers/{filename}.html", 'w', encoding="utf8") as solution_file:
        data = template_file.read().replace('--title--', title).replace('--time--',
                                                                        str(planification_solution[
                                                                                "ExecutionTime"])).replace('--obj--',
                                                                                                           str(
                                                                                                               planification_solution[
                                                                                                                   "Objective"])).replace(
            '--filename--', filename)
        solution_file.write(data)


def visualize_planification_BS(planification_solution, filename, title):
    """
    Create plotly gantt chart from solver Batch Splitting planification solution.
    """
    n = planification_solution['n']
    m = planification_solution['m']
    start_time = datetime.datetime.strptime(planification_solution['planificationStartTime'], '%Y-%m-%d %H:%M:%S.%f')

    data = []
    for i in range(n):
        for ws in range(m):
            if planification_solution["workstationAssignment"][i][ws] == 1:
                data.append(
                    dict(Start=(start_time + datetime.timedelta(seconds=planification_solution['startTime'][i][ws])),
                         Finish=(start_time + datetime.timedelta(
                             seconds=planification_solution['completeTime'][i][ws])),
                         Workstation=planification_solution["workstationNames"][ws],
                         ProductCode=planification_solution["operationProductCode"][i],
                         Batch=planification_solution['Batch'][i][ws]))

    df = pd.DataFrame(data)
    fig = px.timeline(
        df,
        x_start="Start",
        x_end="Finish",
        y="Workstation",
        color="ProductCode",
        text="ProductCode",
        hover_data=['Batch'],
    )
    fig.write_html(f"../db/templates/solvers/planification_{filename}.html", include_plotlyjs=True)
    with open('../solvers/solution_template.html', 'r', encoding="utf8") as template_file, open(
            f"../db/templates/solvers/{filename}.html", 'w', encoding="utf8") as solution_file:
        data = template_file.read().replace('--title--', title).replace('--time--',
                                                                        str(planification_solution[
                                                                                "ExecutionTime"])).replace('--obj--',
                                                                                                           str(
                                                                                                               planification_solution[
                                                                                                                   "Objective"])).replace(
            '--filename--', filename)
        solution_file.write(data)


def create_planification():
    """
    Solve operations planification problem from DB.
    """
    planification_problem = get_planification_problem()

    planification_solution = solve_planification_LS(planification_problem, "cplex", 12, 60)
    with open('../solvers/planification_solution_lotSizing_CPLEX.json', 'w', encoding="utf8") as json_file:
        json.dump(planification_solution, json_file, indent=4, default=str)
    if planification_solution["Status"] in ["SATISFIED", "OPTIMAL_SOLUTION"]:
        visualize_planification_LS(planification_solution, filename="LS_CPLEX", title="Lot Sizing CPLEX")

    planification_solution_z3 = solve_planification_LS_z3(planification_problem, 60)
    with open('../solvers/planification_solution_lotSizing_z3.json', 'w', encoding="utf8") as json_file:
        json.dump(planification_solution, json_file, indent=4, default=str)
    if planification_solution_z3["Status"] in ["sat"]:
        visualize_planification_LS(planification_solution_z3, filename="LS_Z3", title="Lot Sizing Z3")

    planification_solution = solve_planification_BS(planification_problem, "cplex", 12, 60)
    with open('../solvers/planification_solution_batchSplitting_CPLEX.json', 'w', encoding="utf8") as json_file:
        json.dump(planification_solution, json_file, indent=4, default=str)
    if planification_solution["Status"] in ["SATISFIED", "OPTIMAL_SOLUTION"]:
        visualize_planification_BS(planification_solution, filename="BS_CPLEX", title="Batch Splitting CPLEX")

    planification_solution_z3 = solve_planification_BS_z3(planification_problem, 60)
    with open('../solvers/planification_solution_batchSplitting_z3.json', 'w', encoding="utf8") as json_file:
        json.dump(planification_solution, json_file, indent=4, default=str)
    if planification_solution_z3["Status"] in ["sat"]:
        visualize_planification_BS(planification_solution_z3, filename="BS_Z3", title="Batch Splitting Z3")


def bench_solver(planification_problem, model, timeout):
    if model == "LS_CPLEX":
        return solve_planification_LS(planification_problem, "cplex", 12, timeout)
    elif model == "LS_Z3":
        return solve_planification_LS_z3(planification_problem, timeout)
    elif model == "BS_CPLEX":
        return solve_planification_BS(planification_problem, "cplex", 12, timeout)
    else:
        return solve_planification_BS_z3(planification_problem, timeout)


def benchmark_solvers():
    benchmark_data = {}
    with open(f"../solvers/benchmark_results/results.json", 'r') as json_file:
        benchmark_data = json.load(json_file)
    models = ["LS_CPLEX", "LS_Z3", "BS_CPLEX", "BS_Z3"]
    for model in models:
        for depth in [2]:
            for children in [2, 3]:
                with open(f"../solvers/benchmark_dataset/problem_{depth}_{children}.json", 'r') as file:
                    planification_problem = json.load(file)

                    planification_solution = bench_solver(planification_problem, model, 3600)
                    with open(f'../solvers/benchmark_results/solution_{depth}_{children}_{model}.json', 'w',
                              encoding="utf8") as json_file:
                        json.dump(planification_solution, json_file, indent=4, default=str)
                    print(depth, children, planification_solution["Status"], planification_solution["ExecutionTime"])
                    benchmark_data[model][str(depth)][str(children)] = [planification_solution["ExecutionTime"],
                                                                        planification_solution["Status"]]

        # break

    with open('../solvers/benchmark_results/results.json', 'w', encoding="utf8") as json_file:
        json.dump(benchmark_data, json_file, indent=4, default=str)
