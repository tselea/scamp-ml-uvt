import datetime
from minizinc import Instance, Model, Solver

from solvers.templates.minizinc_template import MiniZinc_Template
from solvers.templates.lot_sizing_template import LotSizingTemplate


class Alg_LotSizing_MiniZinc(MiniZinc_Template, LotSizingTemplate):

    def __init__(self, data_source, algorithm_name="LS_MZN", timeout=3600, threads=1, solver="cplex"):
        super().__init__(data_source=data_source, algorithm_name=algorithm_name, timeout=timeout)
        self.threads = threads
        self.solver = solver
        self.config = "../solvers/models/lot_sizing_v2.mzn"

    def _create_instance(self):
        model = Model(self.config)
        solverObj = Solver.lookup(self.solver)
        instance = Instance(solverObj, model)
        instance["n"] = self.planification_problem['n']
        instance["m"] = self.planification_problem['m']
        instance["W"] = self.planification_problem['workstationAssignment']
        instance["t"] = self.planification_problem['assemblyTime']
        instance["d"] = self.planification_problem['operationSuccessor']
        instance["E"] = self.planification_problem['finalOperations']
        instance["finalPosition"] = self.planification_problem['finalOperationPosition']
        instance["D"] = self.planification_problem['finalDeadline']
        instance["M"] = self.planification_problem['M']
        instance["R"] = self.planification_problem['operationReservedTime']
        self.instance = instance

    def _get_planification_solution(self, solution, result):
        solution["startTime"] = result["S"]
        solution["completeTime"] = result["C"]
        n = self.planification_problem['n']
        workstation_assignment = [0] * n
        for operation in range(n):
            workstation_assignment[operation] = self.planification_problem["workstationIDs"][result["A"][operation] - 1]
        solution['workstationAssignment'] = workstation_assignment
        return solution
    
    def _generate_solution(self):
        solution_df = self.generate_dataframe()
        self.scheduling_list = []
        for index, row in solution_df.iterrows():
            ws_id = self.solution['workstationIDs'][self.solution['workstationNames'].index(row['Workstation'])]
            if row['ProductCode'] != "MAINT.":
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

    def generate_dataframe(self):
        return self._generate_dataframe_lot_sizing()
