import datetime

from z3 import Optimize, Int, Real, If, Implies, Or, And, set_param, Sum

from solvers.templates.batch_splitting_template import BatchSplittingTemplate
from solvers.templates.z3_template import Z3_Template

set_param('parallel.enable', True)
set_param('parallel.threads.max', 12)

class Alg_BatchSplittingZ3(Z3_Template, BatchSplittingTemplate):

    def __init__(self, data_source, parsed_alg_input=None,algorithm_name="BS_Z3", timeout=3600):
        super().__init__(data_source, algorithm_name=algorithm_name, timeout=timeout)
        self.scheduling_list = None
        self.ws_occupancy = None
        self.maintenance = None

    def _generate_solution(self):
        solution_df = self.generate_dataframe()
        self.scheduling_list = []
        for index, row in solution_df.iterrows():
            ws_id = self.solution['workstationIDs'][self.solution['workstationNames'].index(row['Workstation'])]
            schedule = {
                'operation_id': row['ID'],
                'operation_code': row['ProductCode'],
                'start_time': row['Start'].to_pydatetime(),
                'end_time': row['Finish'].to_pydatetime(),
                'proc_time': row['Duration'],
                'setup_time': None,
                'ws_id': ws_id,
                'ws_name': row['Workstation'],
                'po_row_id': None,
                'po_id': None,
                'product_id': None
            }
            self.scheduling_list.append(schedule)

        self.ws_occupancy = {}
        start_time = self.solution['planificationStartTime']
        for i in range(self.solution['n']):
            for ws in range(self.solution['m']):
                if self.solution["workstationAssignment"][i][ws] == 1:
                    ws_id = self.solution['workstationIDs'][ws]
                    if ws_id not in self.ws_occupancy:
                        self.ws_occupancy[ws_id] = []
                    self.ws_occupancy[ws_id].append(
                        [start_time + datetime.timedelta(seconds=self.solution['startTime'][i][ws]),
                         start_time + datetime.timedelta(
                             seconds=self.solution['completeTime'][i][ws])])

    def _create_instance(self):
        n = self.planification_problem['n']
        W = self.planification_problem['m']

        instance = Optimize()
        I = [[Int("I_%s_%s" % (i + 1, Y + 1)) for Y in range(W)] for i in range(n)]
        constraint_I = [I[i][Y] == self.planification_problem['workstationAssignment'][i][Y] for Y in range(W) for i in
                        range(n)]
        instance.add(constraint_I)

        t = [[Real("t_%s_%s" % (i + 1, Y + 1)) for Y in range(W)] for i in range(n)]
        constraint_t = [t[i][Y] == self.planification_problem['unitAssemblyTime'][i][Y] for Y in range(W) for i in
                        range(n)]
        instance.add(constraint_t)

        K = [[Real("K_%s_%s" % (i + 1, Y + 1)) for Y in range(W)] for i in range(n)]
        constraint_K = [K[i][Y] == self.planification_problem['setupTime'][i][Y] for Y in range(W) for i in range(n)]
        instance.add(constraint_K)

        b = [Int("b_%s" % (i + 1)) for i in range(n)]
        constraint_b = [b[i] == self.planification_problem['operationProductQuantity'][i] for i in range(n)]
        instance.add(constraint_b)

        R = [Real("R_%s" % (i + 1)) for i in range(n)]
        constraint_R = [R[i] == self.planification_problem['operationReservedTime'][i] for i in range(n)]
        instance.add(constraint_R)

        movesize = Int('movesize')
        instance.add(movesize == 3)
        M = Int('M')
        instance.add(M == self.planification_problem['M'])

        S = [[Real("S_%s_%s" % (i + 1, Y + 1)) for Y in range(W)] for i in range(n)]
        F = [[Real("F_%s_%s" % (i + 1, Y + 1)) for Y in range(W)] for i in range(n)]
        B = [[Int("B_%s_%s" % (i + 1, Y + 1)) for Y in range(W)] for i in range(n)]
        s = [Int("s_%s" % (i + 1)) for i in range(n)]
        constraint_s = [s[i] == self.planification_problem['operationSuccessor'][i] for i in range(n)]
        instance.add(constraint_s)

        A = [[Int("A_%s_%s" % (i + 1, Y + 1)) for Y in range(W)] for i in range(n)]
        constraint_A = [Or(A[i][Y] == 0, A[i][Y] == 1, ) for Y in range(W) for i in range(n)]
        instance.add(constraint_A)

        E = self.planification_problem['finalOperations']
        finalPosition = [Int("finalPosition_%s" % (z + 1)) for z in range(E)]
        constraint_finalPosition = [finalPosition[z] == self.planification_problem['finalOperationPosition'][z] for z in
                                    range(E)]
        instance.add(constraint_finalPosition)

        D = [Real("D_%s" % (z + 1)) for z in range(E)]
        constraint_D = [D[z] == self.planification_problem['finalDeadline'][z] for z in range(E)]
        instance.add(constraint_D)

        constraint_1 = [Sum([If(I[i][Y] == 0, A[i][Y], 0) for Y in range(W) for i in
                             range(n)]) == 0]  # the task cannot be assigned to non-eligible workstations
        # constraint_2 = [Implies(And(Y1 != Y2, s[i] == j+1, A[i][Y1] == 1, A[j][Y2] == 1), S[j][Y2] >= S[i][Y1] + K[i][Y1] - K[j][Y2] + movesize*Sum([A[i][y] for y in range(W)])*t[i][Y1]) for Y1 in range(W)
        #                for Y2 in range(W) for j in range(n) for i in range(n)]

        # constraint_3 = [Implies(And(Y1 != Y2, s[i] == j+1, A[i][Y1] == 1, A[j][Y2] == 1), F[j][Y2] >= F[i][Y1] + + movesize*t[j][Y2]) for Y1 in range(W)
        #                for Y2 in range(W) for j in range(n) for i in range(n)]

        constraint_3b = [Implies(And(s[i] == j + 1, A[i][Y1] == 1, A[j][Y2] == 1), S[j][Y2] >= F[i][Y1]) for Y1 in
                         range(W)
                         for Y2 in range(W) for j in range(n) for i in range(n)]

        constraint_4 = [S[i][Y] >= 0 for Y in range(W) for i in range(n)]
        constraint_5 = [Implies(And(i != j, A[i][Y] == 1, A[j][Y] == 1), Or(F[i][Y] <= S[j][Y], S[i][Y] >= F[j][Y])) for
                        Y in range(W)
                        for j in range(n) for i in range(n)]

        constraint_6 = [Implies(A[i][Y] == 1, And(B[i][Y] > 0, F[i][Y] == S[i][Y] + K[i][Y] + B[i][Y] * t[i][Y])) for Y
                        in range(W) for i in range(n)]
        constraint_7 = [Sum([B[i][Y] for Y in range(W)]) == b[i] for i in range(n)]
        constraint_8 = [Implies(A[i][Y] == 0, And(B[i][Y] == 0, S[i][Y] == 0, F[i][Y] == 0)) for Y in range(W) for i in
                        range(n)]

        constraint_9 = [Implies(And(finalPosition[z] == i + 1, A[i][Y] == 1), F[i][Y] <= D[z]) for Y in range(W) for i
                        in range(n) for z in range(E)]

        constraint_10 = [Implies(And(A[i][Y] == 1, R[i] != -1), S[i][Y] == R[i]) for Y in range(W) for i in range(n)]

        instance.add(constraint_1)
        # instance.add(constraint_2)
        # instance.add(constraint_3)
        instance.add(constraint_3b)
        instance.add(constraint_4)
        instance.add(constraint_5)
        instance.add(constraint_6)
        instance.add(constraint_7)
        instance.add(constraint_8)
        instance.add(constraint_9)
        instance.add(constraint_10)

        self.objective = Real('objective')
        # instance.add(self.objective == sum([S[i][Y] for Y in range(W) for i in range(n)]))
        instance.add(self.objective == self.z3_max(
            [If(And(finalPosition[z] == i + 1, A[i][Y] == 1), F[i][Y], 0) for Y in range(W) for i in range(n) for z in
             range(E)]))
        # instance.add(self.objective == z3_max([F[i][Y] for Y in range(W) for i in range(n)]))
        self.instance = instance

        self.S = S
        self.F = F
        self.A = A
        self.B = B

    def _get_planification_solution(self, solution, result):
        n = self.planification_problem['n']
        W = self.planification_problem['m']
        solution["startTime"] = [[eval(str(result[self.S[i][Y]])) for Y in range(W)] for i in range(n)]
        solution["completeTime"] = [[eval(str(result[self.F[i][Y]])) for Y in range(W)] for i in range(n)]
        solution["Batch"] = [[eval(str(result[self.B[i][Y]])) for Y in range(W)] for i in range(n)]
        solution["workstationAssignment"] = [[eval(str(result[self.A[i][Y]])) for Y in range(W)] for i in range(n)]
        return solution

    def generate_dataframe(self):
        return self._generate_dataframe_batch_splitting()
