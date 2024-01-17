import datetime

from z3 import Optimize, Int, Real, If, Implies, Or, And, set_param

from solvers.templates.lot_sizing_template import LotSizingTemplate
from solvers.templates.z3_template import Z3_Template

set_param('parallel.enable', True)
set_param('parallel.threads.max', 12)


class Alg_LotSizingZ3(Z3_Template, LotSizingTemplate):

    def __init__(self, data_source, parsed_alg_input=None,algorithm_name="LS_Z3", timeout=3600):
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
            ws_id = self.solution["workstationAssignment"][i]
            if ws_id not in self.ws_occupancy:
                self.ws_occupancy[ws_id] = []
            self.ws_occupancy[ws_id].append(
                [start_time + datetime.timedelta(seconds=self.solution['startTime'][i]),
                 start_time + datetime.timedelta(
                     seconds=self.solution['completeTime'][i])])

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

        A = [Int("A_%s" % (i + 1)) for i in range(n)]
        constraint_A = [And(A[i] >= 0, A[i] < m) for i in range(n)]
        instance.add(constraint_A)

        E = self.planification_problem['finalOperations']
        finalPosition = [Int("finalPosition_%s" % (e + 1)) for e in range(E)]
        constraint_finalPosition = [finalPosition[e] == self.planification_problem['finalOperationPosition'][e] for e in
                                    range(E)]
        instance.add(constraint_finalPosition)

        D = [Real("D_%s" % (e + 1)) for e in range(E)]
        constraint_D = [D[e] == self.planification_problem['finalDeadline'][e] for e in range(E)]
        instance.add(constraint_D)

        R = [Real("R_%s" % (i + 1)) for i in range(n)]
        constraint_R = [R[i] == self.planification_problem['operationReservedTime'][i] for i in range(n)]
        instance.add(constraint_R)

        constraint_1 = [Implies(A[i] == w, W[i][w] == 1) for w in range(m) for i in
                        range(n)]  # each task is assigned to exactly one workstation
        constraint_3 = [Implies(A[i] == w, C[i] == S[i] + t[i][w]) for w in range(m) for i in range(n)]
        constraint_4 = [And(S[i] >= 0, C[i] <= M) for i in range(n)]
        constraint_5 = [Implies(And(i != j, d[i] == j + 1), S[j] >= C[i]) for j in range(n) for i in range(n)]
        constraint_6 = [Implies(And(i != j, A[i] == A[j]), Or(C[i] <= S[j], S[i] >= C[j])) for j in range(n) for i in
                        range(n)]
        constraint_7 = [Implies(finalPosition[e] == i + 1, C[i] <= D[e]) for e in range(E) for i in range(n)]
        constraint_8 = [Implies(R[i] != -1, S[i] == R[i]) for i in range(n)]

        instance.add(constraint_1)
        instance.add(constraint_3)
        instance.add(constraint_4)
        instance.add(constraint_5)
        instance.add(constraint_6)
        instance.add(constraint_7)
        instance.add(constraint_8)

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
        for operation in range(n):
            workstation_assignment[operation] = self.planification_problem["workstationIDs"][
                eval(str(result[self.A[operation]]))]
        solution['workstationAssignment'] = workstation_assignment
        return solution

    def generate_dataframe(self):
        return self._generate_dataframe_lot_sizing()
