import datetime
import time

from z3 import If, sat, unsat, set_param

from solvers.templates.solver_template import SolverTemplate

set_param('parallel.enable', True)
set_param('parallel.threads.max', 12)


class Z3_Template(SolverTemplate):

    def __init__(self, data_source, algorithm_name, timeout):
        super().__init__(data_source=data_source, algorithm_name=algorithm_name, timeout=timeout)

        # add solution for api
        self.scheduling_list = None
        self.ws_occupany = None

    def solve(self, timeout=None, po_rowid_list=[]):
        if timeout is None:
            timeout = self.timeout

        self.planification_problem = self.parse_datasource(po_rowid_list)

        start_time = time.time()

        self._create_instance()

        status, result = self._solve_instance(timeout)

        end_time = time.time()
        duration = round(end_time - start_time, 4)

        self.log.debug(f"{self.algorithm_name} {duration}s..")
        self.solution = self._parse_result(status, result)
        self.solution["ExecutionTime"] = duration
        if self.solution["Status"] != "UNSATISFIED":
            self._generate_solution()

        return (self.solution["ExecutionTime"], self.solution["Status"], self.solution["Objective"])

    def _generate_solution(self):
        pass

    def _solve_instance(self, timeout):
        # h = opt.maximize(objective)
        h = self.instance.minimize(self.objective)
        run = 0
        max_runs = 100
        status = unsat
        timeleft = timeout * 1000
        self.instance.set("timeout", timeleft)
        z3_time = time.time()
        result = None
        while run < max_runs and self.instance.check() == sat:
            status = sat
            # self.log.debug(run, timeleft, eval(str(opt.model()[objective])))
            tmp_obj = self.instance.model()[self.objective]
            result = self.instance.model()
            self.instance.add(self.objective < tmp_obj)
            self.instance.minimize(self.objective)
            run += 1

            timeleft -= (time.time() - z3_time) * 1000
            z3_time = time.time()
            self.instance.set("timeout", int(timeleft))
        return status, result

    def _parse_result(self, status, result):
        solution = {}
        solution["Status"] = "SATISFIED" if str(status) == 'sat' else "UNSATISFIED"
        if status == sat:
            solution["Objective"] = eval(str(result[self.objective]))
            for key in ["n", "operationIDs", "operationProductCode", "operationProductQuantity", "m", "workstationIDs",
                        "workstationNames", "planificationStartTime"]:
                solution[key] = self.planification_problem[key]

            solution = self._get_planification_solution(solution, result)
        else:
            solution["Objective"] = -1
        return solution

    def _create_instance(self):
        pass

    def _get_planification_solution(self):
        pass

    def z3_min(self, vs):
        min_var = vs[0]
        for v in vs[1:]:
            min_var = If(v < min_var, v, min_var)
        return min_var

    def z3_max(self, vs):
        max_var = vs[0]
        for v in vs[1:]:
            max_var = If(v > max_var, v, max_var)
        return max_var
