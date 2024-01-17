from z3 import Optimize, Int, Real, If, Implies, Or, And, set_param, Sum

from solvers.templates.lot_sizing_template import LotSizingTemplate
from solvers.templates.z3_template import Z3_Template

set_param('parallel.enable', True)
set_param('parallel.threads.max', 12)


class Alg_LotSizingZ3(Z3_Template, LotSizingTemplate):

    def __init__(self, data_source, timeout=3600):
        super().__init__(data_source, "LotSizingZ3", timeout)

    def _create_instance(self):
        n = self.planification_problem['n']
        m = self.planification_problem['m']

        instance = Optimize()
        W = [[Int("W_%s_%s" % (i + 1, w + 1)) for w in range(m)] for i in range(n)]
        constraint_W = [W[i][w] == self.planification_problem['workstationAssignment'][i][w] for w in range(m) for i in
                        range(n)]
        instance.add(constraint_W)

        t = [[Real("t_%s_%s" % (i + 1, w + 1)) for w in range(m)] for i in range(n)]
        constraint_t = [t[i][w] == self.planification_problem['assemblyTime'][i][w] for w in range(m) for i in range(n)]
        instance.add(constraint_t)

        M = Int('M')
        instance.add(M == self.planification_problem['M'])

        S = [Real("S_%s" % (i + 1)) for i in range(n)]
        C = [Real("C_%s" % (i + 1)) for i in range(n)]
        d = [Int("d_%s" % (i + 1)) for i in range(n)]
        constraint_d = [d[i] == self.planification_problem['operationSuccessor'][i] for i in range(n)]
        instance.add(constraint_d)

        A = [[Int("A_%s_%s" % (i + 1, w + 1)) for w in range(m)] for i in range(n)]
        constraint_A = [Or(A[i][w] == 0, A[i][w] == 1, ) for w in range(m) for i in range(n)]
        instance.add(constraint_A)

        delta = [[Real("delta_%s_%s" % (i + 1, j + 1)) for j in range(n)] for i in range(n)]
        constraint_delta = [Or(delta[i][j] == 0, delta[i][j] == 1, ) for j in range(n) for i in range(n)]
        instance.add(constraint_delta)

        E = self.planification_problem['finalOperations']
        finalPosition = [Int("finalPosition_%s" % (e + 1)) for e in range(E)]
        constraint_finalPosition = [finalPosition[e] == self.planification_problem['finalOperationPosition'][e] for e in
                                    range(E)]
        instance.add(constraint_finalPosition)

        D = [Real("D_%s" % (e + 1)) for e in range(E)]
        constraint_D = [D[e] == self.planification_problem['finalDeadline'][e] for e in range(E)]
        instance.add(constraint_D)

        constraint_1 = [Sum([A[i][w] for w in range(m)]) == 1 for i in
                        range(n)]  # each task is assigned to exactly one workstation
        constraint_2 = [Sum([If(W[i][w] == 0, A[i][w], 0) for w in range(m) for i in
                             range(n)]) == 0]  # the task cannot be assigned to non-eligible workstations
        constraint_3 = [Implies(A[i][w] == 1, C[i] == S[i] + t[i][w]) for w in range(m) for i in range(n)]
        constraint_4 = [And(S[i] >= 0, C[i] <= M) for i in range(n)]
        constraint_5 = [Implies(And(i != j, d[i] == j + 1), S[j] >= C[i]) for j in range(n) for i in range(n)]
        constraint_6 = [Implies(And(i != j, A[i][w] == 1, A[j][w] == 1),
                                And(delta[i][j] + delta[j][i] == 1, S[i] - C[j] >= M * (delta[i][j] - 1))) for w in
                        range(m)
                        for j in range(n) for i in
                        range(n)]  # delta[i,j] = 1 if operation j precedes i (i,j ∈ K,i ̸= j,1≤K≤m), 0 otherwise.
        constraint_7 = [Implies(finalPosition[e] == i + 1, C[i] <= D[e]) for e in range(E) for i in range(n)]

        instance.add(constraint_1)
        instance.add(constraint_2)
        instance.add(constraint_3)
        instance.add(constraint_4)
        instance.add(constraint_5)
        instance.add(constraint_6)
        instance.add(constraint_7)

        self.objective = Real('objective')
        # instance.add(self.objective == sum([S[i] for i in range(n)]))
        # instance.add(self.objective == z3_min([S[i] for i in range(n)]))
        instance.add(
            self.objective == self.z3_max([If(finalPosition[e] == i + 1, C[i], 0) for e in range(E) for i in range(n)]))
        self.instance = instance

        self.S = S
        self.C = C
        self.A = A

    def _get_planification_solution(self, solution, result):
        n = self.planification_problem['n']
        m = self.planification_problem['m']
        solution["startTime"] = [eval(str(result[self.S[i]])) for i in range(n)]
        solution["completeTime"] = [eval(str(result[self.C[i]])) for i in range(n)]

        workstation_assignment = [0] * n
        for workstation in range(m):
            for operation in range(n):
                if result[self.A[operation][workstation]] == 1:
                    workstation_assignment[operation] = self.planification_problem["workstationIDs"][workstation]
        solution['workstationAssignment'] = workstation_assignment
        return solution

    def generate_dataframe(self):
        return self._generate_dataframe_lot_sizing()
