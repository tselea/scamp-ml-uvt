import datetime
import time

import numpy as np

from solvers.templates.solver_template import SolverTemplate


class MiniZinc_Template(SolverTemplate):

    def __init__(self, data_source, algorithm_name, timeout):
        super().__init__(data_source=data_source, algorithm_name=algorithm_name, timeout=timeout)

    def solve(self, threads=None, timeout=None, po_rowid_list=[]):
        if timeout == None:
            timeout = self.timeout
        if threads == None:
            threads = self.threads

        self.planification_problem = self.parse_datasource(po_rowid_list)

        start_time = time.time()

        self._create_instance()

        result = self._solve_instance(timeout, threads)

        end_time = time.time()
        duration = round(end_time - start_time, 4)

        self.log.debug(f"{self.algorithm_name} {duration}s..")
        self.solution = self._parse_result(result)
        self.solution["ExecutionTime"] = duration
        if self.solution["Status"] != "UNSATISFIED":
            self._generate_solution()

        return (self.solution["ExecutionTime"], self.solution["Status"], self.solution["Objective"])

    def _solve_instance(self, timeout, threads):
        return self.instance.solve(timeout=datetime.timedelta(seconds=timeout), processes=threads,
                                   intermediate_solutions=False)

    def _parse_result(self, result):
        solution = {}
        if result:
            solution["Status"] = str(result.status)
            solution["Objective"] = np.round(result["objective"])
            if result.status is result.status.SATISFIED or result.status is result.status.OPTIMAL_SOLUTION:
                for key in ["n", "operationIDs", "operationProductCode", "operationProductQuantity", "m",
                            "workstationIDs", "workstationNames", "planificationStartTime"]:
                    solution[key] = self.planification_problem[key]

                solution = self._get_planification_solution(solution, result)
        else:
            solution["Status"] = "UNSATISFIED"
            solution["Objective"] = -1
        return solution

    def _create_instance(self):
        pass

    def _get_planification_solution(self):
        pass
    
    def _generate_solution(self):
        pass