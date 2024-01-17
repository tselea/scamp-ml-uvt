from pathlib import Path

import numpy as np
import plotly.express as px

from solutions.algorithm_template import AlgorithmTemplate


class SolverTemplate(AlgorithmTemplate):

    def __init__(self, data_source, algorithm_name, timeout=3600):
        super().__init__(data_source=data_source, algorithm_name=algorithm_name)
        self.planification_problem = None
        self.solution = None
        self.timeout = timeout

    def parse_datasource(self, po_rowid_list=[]):
        operations = self.data_source.operationDS.get_all_operations_for_product_commands(po_rowid_list)
        operations.sort(key=lambda op: op.id)
        operation_n = len(operations)
        if operation_n==0:
            raise Exception("No operations to schedule")
        deadlines = [final_operation.deliverydate for final_operation in filter(lambda op: op.parentoperationid == None, operations)]

        maintenances = self.data_source.maintenanceDS.get_maintenances(interval_start_date = self.data_source.startTime, interval_end_date=max(deadlines))
        maintenance_n = len(maintenances)

        planification_problem = {}
        planification_problem['operationIDs'] = [op.id for op in operations] + [maintenance.id for maintenance in
                                                                                maintenances]
        n = operation_n + maintenance_n
        planification_problem['n'] = n
        planification_problem['operationProductCode'] = [op.productcode for op in operations] + [
            "Maintenance" for maintenance in maintenances]
        planification_problem['operationProductQuantity'] = [op.quantity for op in operations] + [1] * maintenance_n
        planification_problem['operationSuccessor'] = [-1 if op.parentoperationid is None
                                                       else planification_problem['operationIDs']
                                                       .index(op.parentoperationid) + 1 for op in operations] + [-1] * maintenance_n

        product_stations = self.data_source.workstationDS.get_product_stations_by_product_ids(
            list(set([op.productid for op in operations])))
        planification_problem['workstationIDs'] = list(set([ps.stationid.id for ps in product_stations] + [m.stationid.id for m in maintenances]))
        planification_problem['workstationNames'] = [ws for ws in self.data_source.stationsDS.get_stations_by_ids(
            planification_problem['workstationIDs'])]

        m = len(planification_problem['workstationIDs'])
        planification_problem['m'] = m
        planification_problem['workstationAssignment'] = np.zeros((n, m), dtype=np.int8).tolist()
        planification_problem['assemblyTime'] = np.zeros((n, m)).tolist()
        planification_problem['unitAssemblyTime'] = np.zeros((n, m)).tolist()
        planification_problem['setupTime'] = np.zeros((n, m)).tolist()
        for operation in operations:
            for product_station in self.data_source.workstationDS.get_product_stations_by_product_ids(
                    [operation.productid]):
                planification_problem['workstationAssignment'][planification_problem['operationIDs'].index(
                    operation.id)][planification_problem['workstationIDs'].index(product_station.stationid.id)] = 1
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

        planification_problem['operationReservedTime'] = [-1] * n
        for maintenance in maintenances:
            planification_problem['workstationAssignment'][planification_problem['operationIDs'].index(
                maintenance.id)][planification_problem['workstationIDs'].index(maintenance.stationid.id)] = 1
            planification_problem['assemblyTime'][planification_problem['operationIDs'].index(maintenance.id)][
                planification_problem['workstationIDs'].index(
                    maintenance.stationid.id)] = (
                        maintenance.maintenancestop - maintenance.maintenancestart).total_seconds()
            planification_problem['unitAssemblyTime'][planification_problem['operationIDs'].index(maintenance.id)][
                planification_problem['workstationIDs'].index(
                    maintenance.stationid.id)] = (
                        maintenance.maintenancestop - maintenance.maintenancestart).total_seconds()
            planification_problem['operationReservedTime'][
                planification_problem['operationIDs'].index(maintenance.id)] = (
                maintenance.maintenancestart - self.data_source.startTime).total_seconds()

        planification_problem['finalOperationIDs'] = [op.id for op in
                                                      filter(lambda op: op.parentoperationid == None, operations)]
        planification_problem['finalOperationPosition'] = [planification_problem['operationIDs'].index(x) + 1 for x in
                                                           planification_problem['finalOperationIDs']]
        planification_problem['finalOperations'] = len(planification_problem['finalOperationIDs'])
        planification_problem['finalDeadline'] = [0] * planification_problem['finalOperations']

        planification_problem['planificationStartTime'] = self.data_source.startTime

        for final_operation in filter(lambda op: op.parentoperationid == None, operations):
            planification_problem['finalDeadline'][
                planification_problem['finalOperationIDs'].index(final_operation.id)] = (
                final_operation.deliverydate - self.data_source.startTime).total_seconds()
        planification_problem['M'] = int(max(planification_problem['finalDeadline'])) + 1

        return (planification_problem)

    def generate_plot(self, output_path):
        dataframe = self.generate_dataframe()
        if not dataframe.empty:
            fig = px.timeline(
                dataframe,
                x_start="Start",
                x_end="Finish",
                y="Workstation",
                color="ProductCode",
                text="ProductCode",
                hover_data=["Quantity", "Duration", "ID"],
            )
            fig.update_yaxes(categoryorder='category ascending')
            output_dir = Path(f"{output_path}")
            output_dir.mkdir(parents=True, exist_ok=True)

            dataframe.to_csv(output_dir / f"{self.algorithm_name}_{self.data_source.sourceName}.csv", index=False)
            fig.write_html(output_dir / f"{self.algorithm_name}_{self.data_source.sourceName}.html",
                           include_plotlyjs=True)
            fig.write_image(output_dir / f"{self.algorithm_name}_{self.data_source.sourceName}.png", width=1020,
                            height=480)
