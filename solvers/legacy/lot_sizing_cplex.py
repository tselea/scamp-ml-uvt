from minizinc import Instance, Model, Solver

from solvers.templates.minizinc_template import MiniZinc_Template
from solvers.templates.lot_sizing_template import LotSizingTemplate


class Alg_LotSizingCPLEX(MiniZinc_Template, LotSizingTemplate):

    def __init__(self, data_source, timeout=3600, threads=1):
        super().__init__(data_source=data_source, algorithm_name="LotSizingCPLEX", timeout=timeout)
        self.threads = threads
        self.config = "../solvers/models/lot_sizing.mzn"
        self.solver = "cplex"

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
        self.instance = instance

    def _get_planification_solution(self, solution, result):
        solution["startTime"] = result["S"]
        solution["completeTime"] = result["C"]
        n, m = self.planification_problem['n'], self.planification_problem['m']
        workstation_assignment = [0] * n
        for workstation in range(m):
            for operation in range(n):
                if result["A"][operation][workstation] == 1:
                    workstation_assignment[operation] = self.planification_problem["workstationIDs"][workstation]
        solution['workstationAssignment'] = workstation_assignment
        return solution

    def generate_dataframe(self):
        return self._generate_dataframe_lot_sizing()
