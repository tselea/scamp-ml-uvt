import datetime
from minizinc import Instance, Model, Solver

from solvers.templates.batch_splitting_template import BatchSplittingTemplate
from solvers.templates.minizinc_template import MiniZinc_Template


class Alg_BatchSplitting_MiniZinc(MiniZinc_Template, BatchSplittingTemplate):

    def __init__(self, data_source, algorithm_name="BS_MZN", timeout=3600, threads=1, solver="cplex"):
        super().__init__(data_source=data_source, algorithm_name=algorithm_name, timeout=timeout)
        self.threads = threads
        self.solver = solver
        self.config = "../solvers/models/batch_splitting_v2.mzn"
    
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
                    'product_id': None,
                    'quantity':row['quantity']
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
        model = Model(self.config)
        solverObj = Solver.lookup(self.solver)
        instance = Instance(solverObj, model)
        instance["W"] = self.planification_problem['m']
        instance["n"] = self.planification_problem['n']
        instance["I"] = self.planification_problem['workstationAssignment']

        instance["t"] = self.planification_problem['unitAssemblyTime']
        instance["K"] = self.planification_problem['setupTime']
        instance["b"] = self.planification_problem['operationProductQuantity']

        instance["s"] = self.planification_problem['operationSuccessor']
        instance["E"] = self.planification_problem['finalOperations']
        instance["finalPosition"] = self.planification_problem['finalOperationPosition']
        instance["D"] = self.planification_problem['finalDeadline']
        instance["M"] = self.planification_problem['M']
        instance["R"] = self.planification_problem['operationReservedTime']
        instance["movesize"] = 3
        self.instance = instance

    def _get_planification_solution(self, solution, result):
        solution["startTime"] = result["S"]
        solution["completeTime"] = result["F"]
        solution['workstationAssignment'] = result["A"]
        solution['Batch'] = result["B"]
        return solution

    def generate_dataframe(self):
        return self._generate_dataframe_batch_splitting()
