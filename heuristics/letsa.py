import datetime
import logging
import time
import copy
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px

# import db.dao.workstation as wsQueries
from db.models import ProductStation, Product, Station
from heuristics.machine_split import Machine_Split_Z3
from product_bom.operation import Operation as Op
from solutions.algorithm_template import AlgorithmTemplate
#import logging

#logger = logging.getLogger(__name__)


class Alg_LETSA(AlgorithmTemplate):

    def __init__(self, data_source, parsed_alg_input=None, algorithm_name="LETSA", logging_level=logging.WARNING, machine_selection_type="original"):
        """
        LETSA algorithm
        :param data_source: the data source for operations, database or  JSON files
        :param logging_level:
        :param machine_selection_type: the variant used to select the machine on which the operation is executed: original, solver
        """
        super().__init__(data_source, algorithm_name, logging_level)
        self.scheduling_list = []
        self.ws_occupancy = []
        self.maintenance = None
        self.machine_selection_type = machine_selection_type

    def _compute_network_paths(self, operation_list):
        network_paths = []
        for current_operation in operation_list:
            network_paths.extend(self.get_network_paths(current_operation))
        return network_paths

    def solve(self, po_rowid=None, po_rowid_list=[], processing_time='min'):

        # print('start_time', self.data_source.startTime)

        # Step 3
        # get all feasible operations-operation that do not have any other succeeding operation (no parent operations)
        feasible_operation_list = []
        if len(po_rowid_list) > 0:
            for po_rowid in po_rowid_list:
                feasible_operation_list.extend(self.data_source.operationDS.get_parent_operations(po_rowid))
        else:
            feasible_operation_list = self.data_source.operationDS.get_parent_operations(po_rowid)


        #logger.debug(f"Initial feasible list is {feasible_operation_list}")

        scheduling_list = []

        ws_occupancy = self.data_source.maintenanceDS.get_maintenance_intervals()

        alg_start_time = time.time()

        planned_operations = []
        iteration_number = 0
        l = [(op.id, op.productcode) for op in feasible_operation_list]
        self.log.debug(f"Starting feasibile list:{l}")

        # pre-compute network paths and the corresponding cumm proc time (with max)
        network_paths = self._compute_network_paths(feasible_operation_list)
        network_paths_lengths = []
        network_paths_proc_details = []
        for net_path in network_paths:
            cumultative_proc_time, cumultative_proc_details = self.get_cumulative_proc_time(net_path,
                                                                                            processing_time='max')
            network_paths_lengths.append(cumultative_proc_time)
            network_paths_proc_details.append(cumultative_proc_details)

        # Step 4
        current_operation_start_time = 0
        while len(feasible_operation_list) > 0:
            iteration_number += 1
            self.log.debug(f"Iteration number {iteration_number}")

            # show length of path
            self.log.debug(f"Step 4.1 Network paths - Step 4.2 Length of path :")
            for i, net in enumerate(network_paths):
                l = [(op.id, op.productcode) for op in net]
                self.log.debug(f"{l} - {round(network_paths_lengths[i], 2)}")

            # Determine the critical (largest cumulative processing time) path and select the operation of the critical path
            # that also belongs to the feasible list F, randonmly in our implementation its the first for more max
            # Step 4.3
            max_path_index = np.argmax(network_paths_lengths)

            selected_operation = None
            for op in network_paths[max_path_index]:
                for i, op_f in enumerate(feasible_operation_list):
                    if op == op_f:
                        selected_operation = op_f
                        break
                if i < len(feasible_operation_list) - 1:
                    break

            self.log.debug(f"Step 4.3 Operation selected: {op.id}-{op.productcode}")

            # Set its tentative completion time
            # Step 4.4
            completion_time_t = selected_operation.deliverydate

            # start_time_t = completion_time_t - datetime.timedelta(seconds=product_assem_time)
            schedule_operation = {'operation_id': selected_operation.id,
                                  'operation_code': selected_operation.productcode, 'start_time': None,
                                  'end_time': None,
                                  'proc_time': None,
                                  'setup_time': None, 'ws_id': None, 'ws_name': None,
                                  'po_row_id': selected_operation.purchaseorderrowid,
                                  'po_id': selected_operation.purchaseorderid,
                                  'product_id': selected_operation.productid,
                                  'quantity': selected_operation.quantity
                                  }

            # For each machine included in the required work-center
            # Step 4.5
            # operation_id_ws = network_paths_proc_details[max_path_index][selected_operation.id]["ws_id"]
            operation_id_ws = network_paths_proc_details[max_path_index][selected_operation.id]
            #try:
            if self.machine_selection_type == "original":
                current_operation_start_time = self.assignWorkStation(operation_id_ws, ws_occupancy, schedule_operation,
                                                                      scheduling_list, completion_time_t, alg_start_time)
            else:
                current_operation_start_time = self.assignWorkStation_Z3(operation_id_ws, ws_occupancy, schedule_operation,
                                                                         scheduling_list, completion_time_t, selected_operation.quantity)
            #except Exception:
            if current_operation_start_time is None:
                execution_time = round(time.time() - alg_start_time, 4)
                self.makespan = None
                return (execution_time, "UNSATISFIED", -1)
            # Delete operation  from the operation network
            # Step 4.7
            # TODO si sterse practic din tabel?
            planned_operations.append(selected_operation)
            feasible_operation_list.remove(selected_operation)

            # remove operation for network path
            delete_net_paths = []
            for i in range(len(network_paths)):
                net_path = network_paths[i]
                if net_path[0].id == selected_operation.id:
                    network_paths[i].pop(0)
                    proc_time = \
                        max(network_paths_proc_details[i][selected_operation.id],
                            key=lambda x: x['product_assem_time'])[
                            'product_assem_time']
                    network_paths_lengths[i] -= proc_time
                if len(network_paths[i]) < 1:
                    delete_net_paths.append(i)

            for i in sorted(delete_net_paths, reverse=True):
                del (network_paths[i])
                del (network_paths_lengths[i])
                del (network_paths_proc_details[i])

            op_descendants = self.data_source.operationDS.get_by_parent_operation(selected_operation)
            # TODO check if this step is alright
            # add delivery date to the descendants as starting date of parent
            for op in op_descendants:
                updated_op = self.data_source.operationDS.update_delivery_date(op, current_operation_start_time)
                #!!!!!!
                feasible_operation_list.append(updated_op)

            l = [(op.id, op.productcode) for op in feasible_operation_list]
            self.log.debug(f"Step 4.7/4.8 New feasabile list:{l}")

        self.log.debug(f"Sheduling list:{scheduling_list}")
        min_date = min([op["start_time"] for op in scheduling_list])
        max_date = max([op["end_time"] for op in scheduling_list])

        # Add maintenance operations
        # for maintenance in self.data_source.maintenanceDS.get_maintenances():
        #     schedule_operation = {'operation_id': maintenance.id,
        #                           'operation_code': "Maintenance",
        #                           'start_time': maintenance.maintenancestart,
        #                           'end_time': maintenance.maintenancestop, 'proc_time': (
        #                     maintenance.maintenancestop - maintenance.maintenancestart).total_seconds(),
        #                           'setup_time': 0, 'ws_id': maintenance.stationid.id}
        #     schedule_operation['ws_name'] = self.data_source.stationsDS.get_by_id(schedule_operation['ws_id'])
        #     scheduling_list.append(schedule_operation)

        execution_time = round(time.time() - alg_start_time, 4)

        self.scheduling_list = scheduling_list
        self.ws_occupancy = ws_occupancy

        # print(execution_time)
        self.log.debug(f'({execution_time}, "SATISFIED", {(max_date - min_date).total_seconds()}')
        self.makespan = (max_date - min_date).total_seconds()
        return (execution_time, "SATISFIED", (max_date - min_date).total_seconds())

    def assignWorkStation_Z3(self, operation_id_ws, ws_occupancy, schedule_operation, scheduling_list, completion_time_t,
                             quantity=None):
        stations = []
        for ws in operation_id_ws:
            #print("....ws:",ws)
            ps = self.data_source.workstationDS.get_by_productid_and_stationid(schedule_operation['product_id'], ws['ws_id'][0])
            for _id_ws in ws['ws_id']:
                 stations.append(Machine_Split_Z3.Item(ps.setuptime, ps.cycletime, ps.estimatedoee, _id_ws))

        alg = Machine_Split_Z3(quantity, stations, self.data_source.startTime, completion_time_t, ws_occupancy, variant=self.machine_selection_type)
        quatitySplit, startTime, durationTime = alg.solve()
        #print("...rez",quatitySplit, startTime, durationTime, stations)


        index = 0

        for station in stations:
            #print("..station", station, " cantitate:", quatitySplit[index])
            if quatitySplit[index] != 0:
                aux_schedule_operation = copy.deepcopy(schedule_operation)
                aux_schedule_operation['ws_id'] = station.id
                aux_schedule_operation['start_time'] = datetime.datetime.fromtimestamp(startTime[index])
                aux_schedule_operation['end_time'] = datetime.datetime.fromtimestamp(startTime[index]) + datetime.timedelta(seconds=float(durationTime[index]))
                aux_schedule_operation['ws_name'] = self.data_source.stationsDS.get_by_id(aux_schedule_operation['ws_id'])
                aux_schedule_operation['proc_time'] = durationTime[index]
                aux_schedule_operation['quantity'] = quatitySplit[index]
                # adaugare - am un for
                scheduling_list.append(aux_schedule_operation)
                #print(ws_occupancy)
                if station.id not in ws_occupancy: ws_occupancy[station.id] = []
                ws_occupancy[station.id].append([aux_schedule_operation['start_time'], aux_schedule_operation['end_time']])
                if completion_time_t > aux_schedule_operation['start_time']:
                    completion_time_t = aux_schedule_operation['start_time']
            index += 1
        #print(".......completion_time_t:", completion_time_t, ws_occupancy)
        return completion_time_t

    def assignWorkStation(self, operation_id_ws, ws_occupancy, schedule_operation, scheduling_list, completion_time_t, alg_start_time):
        self.log.debug(f"!!!!!!!completion_time_t: {completion_time_t}")
        # min_product_asssem_time = min(operation_id_ws, key=lambda x:x['product_assem_time'])
        selected_ws = None
        proposed_sch = {}
        # find interval on all the ws
        for ws in operation_id_ws:
            product_assem_time = ws['product_assem_time']
            for ws_id in ws['ws_id']:
                start_time = completion_time_t - datetime.timedelta(seconds=float(ws['product_assem_time']))
                completion_time = completion_time_t
                # Identify the latest available starting time for operation
                # Step 4.5.1
                # TODO recheck find the available time interval

                if ws_id in ws_occupancy:
                    for i, interval in reversed(list(enumerate(ws_occupancy[ws_id]))):
                        start = interval[0]
                        end = interval[1]
                        # plan here
                        if start_time <= end:
                            if start_time + datetime.timedelta(seconds=float(product_assem_time)) > start:
                                # move start_time
                                start_time = start - datetime.timedelta(seconds=float(product_assem_time))
                                completion_time = start_time + datetime.timedelta(seconds=float(product_assem_time))

                #print({'start_time': start_time, 'completion_time': completion_time,
                #                            'product_assem_time': product_assem_time})
                if start_time >= self.data_source.startTime:
                    proposed_sch[ws_id] = {'start_time': start_time, 'completion_time': completion_time,
                                           'product_assem_time': product_assem_time}
                 #   print("Trece data")

        # select the ws latest completion, latest start
        for ws_id, info in proposed_sch.items():
            if selected_ws:
                if info['completion_time'] > proposed_sch[selected_ws]['completion_time']:
                    selected_ws = ws_id
                elif info['completion_time'] == proposed_sch[selected_ws]['completion_time']:
                    if info['start_time'] > proposed_sch[selected_ws]['start_time']:
                        selected_ws = ws_id
            else:
                selected_ws = ws_id
            #print ("Masina aleasa", selected_ws)

        # assign the operation on selected ws
        self.log.debug(f'Selected WS is {selected_ws}')
        if selected_ws is not None:
            schedule_operation['ws_id'] = selected_ws
            schedule_operation['start_time'] = proposed_sch[selected_ws]['start_time']
            schedule_operation['end_time'] = proposed_sch[selected_ws]['completion_time']
            if selected_ws not in ws_occupancy:
                ws_occupancy[selected_ws] = []
            ws_occupancy[selected_ws].append([schedule_operation['start_time'], schedule_operation['end_time']])
            ws_occupancy[selected_ws] = sorted(ws_occupancy[selected_ws], key=lambda x: x[0])

            self.log.debug(
                f"Step 4.5 Scheduled start/completion: {schedule_operation['start_time']}/{schedule_operation['end_time']}")
        else:
            #raise Exception('Could not schedule operation.')
            self.log.info(f'Could not schedule operation.')
            return None

        # Schedule operation at the latest available starting time Se on the corresponding machine.
        # Step 4.6

        # update with work station name
        schedule_operation['ws_name'] = self.data_source.stationsDS.get_by_id(schedule_operation['ws_id'])
        schedule_operation['proc_time'] = proposed_sch[selected_ws]['product_assem_time']

        # adaugare - am un for
        scheduling_list.append(schedule_operation)
        self.log.debug(f"Step 4.6 Selected work station: {schedule_operation['ws_id']}")
        # print(schedule_operation)

        return schedule_operation['start_time']

    def get_network_paths(self, operation):
        path = []
        all_paths = []
        self.get_network_pathsRec(operation, path, 0, all_paths)
        return all_paths

    def get_network_pathsRec(self, root_operation, path, pathLen, all_paths):

        if len(path) > pathLen:
            path[pathLen] = root_operation
        else:
            path.append(root_operation)

        pathLen = pathLen + 1

        # check if leaf node
        # children = list(Operation.objects.filter(parentproductid=root_operation.productid).using("scampml_uvt"))
        children = self.data_source.operationDS.get_by_parent_operation(root_operation)
        if len(children) == 0:
            # leaf node
            all_paths.append(path[0:pathLen])
        else:
            # call the function for each child
            for child in children:
                self.get_network_pathsRec(child, path, pathLen, all_paths)

    def get_processing_time(self, operation, processing_time):
        selection_time = {
            'max': max,
            'min': min
        }

        proc_time_list = []
        ws_list = self.data_source.workstationDS.get_product_stations(operation.productid)
        for ws in ws_list:
            # TODO compute product assem time if cycle time is not 1
            product_assem_time = (ws.estimatedoee * ws.cycletime) * operation.quantity + ws.setuptime
            # print("operation", operation, "product_assem_time", product_assem_time)
            index = -1
            for i, prod_assem_details in enumerate(proc_time_list):
                if prod_assem_details['product_assem_time'] == product_assem_time and prod_assem_details[
                        'setup_time'] == ws.setuptime:
                    # we have an identical machine
                    index = i
            if index == -1:
                proc_time_list.append(
                    {'product_assem_time': product_assem_time, 'setup_time': ws.setuptime, 'ws_id': [ws.stationid.id]})
            else:
                proc_time_list[index]['ws_id'].append(ws.stationid.id)

        result = selection_time.get(processing_time)(proc_time_list, key=lambda x: x['product_assem_time'])

        # print (result, proc_time_list)
        return result, proc_time_list

    def get_cumulative_proc_time(self, network_path, processing_time):
        total = 0
        total_detailed = {}
        for op in network_path:
            op_proc_time, op_proc_time_list = self.get_processing_time(op, processing_time)
            total += op_proc_time['product_assem_time']
            total_detailed[op.id] = op_proc_time_list

        return total, total_detailed


    def letsa_example(insert_op=True, insert_ps=True):
        if insert_op:
            operation = Op(100, 'A.20', 'A.20', po_row_id=1005, po_id=0, parent=None,
                           children_list=[],
                           quantity=1, parent_op=None,
                           delivery_date=datetime.datetime.now())
            op_db_parent = operation.insert_db()

            operation = Op(100, 'A.10', 'A.10', po_row_id=1005, po_id=0, parent=100,
                           children_list=[],
                           quantity=1, parent_op=op_db_parent.id,
                           delivery_date=None)
            op_db = operation.insert_db()

            operation = Op(200, 'C.10', 'C.10', po_row_id=1005, po_id=0, parent=100,
                           children_list=[],
                           quantity=1, parent_op=op_db_parent.id,
                           delivery_date=None)
            op_db_parent = operation.insert_db()

            operation = Op(300, 'D.10', 'D.10', po_row_id=1005, po_id=0, parent=300,
                           children_list=[],
                           quantity=1, parent_op=op_db_parent.id,
                           delivery_date=None)
            op_db = operation.insert_db()

            operation = Op(400, 'F.20', 'F.20', po_row_id=1005, po_id=0, parent=300,
                           children_list=[],
                           quantity=1, parent_op=op_db_parent.id,
                           delivery_date=None)
            op_db_parent = operation.insert_db()

            operation = Op(500, 'F.10', 'F.10', po_row_id=1005, po_id=0, parent=400,
                           children_list=[],
                           quantity=1, parent_op=op_db_parent.id,
                           delivery_date=None)
            op_db = operation.insert_db()

        if insert_ps:
            st_1 = Station.objects.filter(id=1).using("scampml")[0]
            st_2 = Station.objects.filter(id=2).using("scampml")[0]

            p = Product(id=100, code='A.20', name='A.20')
            p.save(using='scampml')
            ps = ProductStation(id=22, productid=p, stationid=st_2,
                                cycletime=86.4, cyclequantity=1, setuptime=5, estimatedoee=200)
            ps.save(using='scampml')

            p = Product(id=200, code='A.10', name='A.10')
            p.save(using='scampml')
            ps = ProductStation(id=23, productid=p, stationid=st_1,
                                cycletime=86.400, cyclequantity=1, setuptime=10, estimatedoee=500)
            ps.save(using='scampml')

            p = Product(id=300, code='C.10', name='C.10')
            p.save(using='scampml')
            ps = ProductStation(id=24, productid=p, stationid=st_1,
                                cycletime=86.400, cyclequantity=1, setuptime=10, estimatedoee=100)
            ps.save(using='scampml')

            p = Product(id=400, code='F.20', name='F.20')
            p.save(using='scampml')
            ps = ProductStation(id=25, productid=p, stationid=st_1,
                                cycletime=86.400, cyclequantity=1, setuptime=10, estimatedoee=300)
            ps.save(using='scampml')

            p = Product(id=500, code='D.10', name='D.10')
            p.save(using='scampml')
            ps = ProductStation(id=26, productid=p, stationid=st_1,
                                cycletime=86.400, cyclequantity=1, setuptime=10, estimatedoee=300)
            ps.save(using='scampml')

            p = Product(id=600, code='F.10', name='F.10')
            p.save(using='scampml')
            ps = ProductStation(id=27, productid=p, stationid=st_2,
                                cycletime=86.400, cyclequantity=1, setuptime=10, estimatedoee=200)
            ps.save(using='scampml')
