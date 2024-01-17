from minizinc import Instance, Model, Solver

from solvers.templates.batch_splitting_template import BatchSplittingTemplate
from solvers.templates.minizinc_template import MiniZinc_Template


class Alg_BatchSplittingCPLEX(MiniZinc_Template, BatchSplittingTemplate):

    def __init__(self, data_source, timeout=3600, threads=1):
        super().__init__(data_source=data_source, algorithm_name="BatchSplittingCPLEX", timeout=timeout)
        self.threads = threads
        self.config = "../solvers/models/batch_splitting.mzn"
        self.solver = "cplex"

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
