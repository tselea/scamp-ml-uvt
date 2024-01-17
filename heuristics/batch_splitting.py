import copy
import datetime
import json
import logging
import math
import time
from pathlib import Path

from db.models import Station, Product, ProductStation
from product_bom.operation import Operation as Op
from solutions.algorithm_template import AlgorithmTemplate
import plotly.express as px
import pandas as pd



class Alg_B_SPLIT(AlgorithmTemplate):

    def __init__(self, data_source, parsed_alg_input=None,logging_level=logging.WARNING):
        super().__init__(data_source, "BSPLIT", logging_level)
        self.b_split_intervals = None
        self.b_split_proc_times = None

        self.scheduling_list = None
        self.ws_occupany = None

    def get_op_workstations(self, operation_list):

        # step1 - find all stations where operation can be executed and fill the replicates
        stations_id = set()
        for op in operation_list:
            pst_list = self.data_source.workstationDS.get_product_stations(op.productid)
            for st in pst_list:
                stations_id.add(st.stationid.id)

        ws_info = self.data_source.stationsDS.get_stations_replications(stations_id)
        # print("ws_info", ws_info)

        # ws_info = {}
        for op in operation_list:
            product_id = op.productid
            # get workstations from database
            pst_list = self.data_source.workstationDS.get_product_stations(product_id)

            for rep_id, values in ws_info.items():
                found = True

                if len(pst_list) != len(values["replicates"]): continue

                for st in pst_list:
                    if st.stationid not in values["replicates"]:
                        found = False

                if found:
                    if st.stationid in values["replicates"]:
                        # TODO ?Q @Teodora aici a avut impact schimbare operations pe set, este importanta ordinea ?
                        # operations = values.get("operations", set())
                        # operations.add(op)
                        # ws_info[rep_id]["operations"] = operations
                        operations = values.get("operations", [])
                        if op not in operations:
                            operations.append(op)
                            ws_info[rep_id]["operations"] = operations

            # st =self.data_source.stationsDS.get_by_id(st.stationid.id)

            # # TODO maybe a different way to find duplicates, not by name
            # #for st in op_st_list:
            # st_name = st.name
            # st_type = st_name[2]
            # if st_type not in ws_info:
            #     ws_info[st_type] = {'replicates': [], 'operations': []}
            # if st not in ws_info[st_type]['replicates']:
            #     ws_info[st_type]['replicates'].append(st)
            # if op not in ws_info[st_type]['operations']:
            #     ws_info[st_type]['operations'].append(op)

        print("ws_info", ws_info)

        return ws_info

    def solve(self, po_rowid=2000, po_rowid_list=[], scheduling_example_file=None):
        self.alg_start_time = time.time()
        self.b_split(po_rowid=po_rowid, po_rowid_list=po_rowid_list, split_by_piece=True)
        self.b_sched(po_rowid=po_rowid,po_rowid_list=po_rowid_list,
                     scheduling_example_file=scheduling_example_file)

    def b_split(self, po_rowid=2000,po_rowid_list=[], split_by_piece=False):
        final_scheduling_dict = {}

        # get all operations
        # q_object_filter = None
        # if po_rowid is not None:
        #     q_object_filter = Q(purchaseorderrowid=po_rowid)
        # op_list = opQueries.get_operations(q_object_filter)
        op_list = []
        if len(po_rowid_list) > 0:
            for po_rowid in po_rowid_list:
                op_list.extend(self.data_source.operationDS.get_all_operations_for_product_command(po_rowid))
        else:
            op_list = self.data_source.operationDS.get_all_operations_for_product_command(po_rowid)



        # get all workcenters/workstations
        ws_info = self.get_op_workstations(op_list)
        processing_times = []
        for ws_id, ws_op in ws_info.items():
            # Step 1. Take the n operations and process them one after another on a single replicate. Compute makespan.
            # take the first replicate
            # makespan is the letsa product_assem_time
            makespan = 0
            schedule_list = []
            ws_operations = ws_op['operations']
            current_replicate = ws_op['replicates'][0]
            start = 0
            # print(ws_id, ws_operations)
            for op in ws_operations:
                # q_object_filter = Q(productid=op.productid) & Q(stationid=current_replicate.id)
                # product_stations = wsQueries.get_all_product_stations(q_object_filter)[0]
                product_stations = self.data_source.workstationDS.get_by_productid_and_stationid(op.productid,
                                                                                                 current_replicate.id)

                product_assem_time = (
                                             product_stations.estimatedoee * product_stations.cycletime) * op.quantity + product_stations.setuptime
                product_assem_time = float(product_assem_time)
                makespan += product_assem_time
                end = start + product_assem_time
                one_product_time = product_stations.estimatedoee * product_stations.cycletime
                schedule_list.append({'op_id': op.id, 'product_id': op.productid, 'product_name': op.productname,
                                      'product_code': op.productcode, 'setup_time': float(product_stations.setuptime),
                                      'product_assem_time': float(product_assem_time), 'start': start, 'end': end,
                                      'one_product_time': float(one_product_time)})
                start = end

            self.log.debug(f"Step 1. Workcenter:{ws_id}. Computed makespan {round(makespan, 2)}")
            self.log.debug(f"Step 1. Scheduling (in any sequence):")

            def print_schedule(schedule_list):
                for sch in schedule_list:
                    self.log.debug(
                        f"Operation {sch['op_id']}, product {sch['product_name']}-[{sch['start']};{sch['end']}]-setup_time:{sch['setup_time']}")

            print_schedule(schedule_list)
            processing_times.extend(copy.deepcopy(schedule_list))
            # number of replicates
            makespan = float(makespan)
            m = len(ws_op['replicates'])
            part = math.ceil(makespan / m)
            makespan = m * part
            self.log.debug(f"Step 2. Workcenter:{ws_id}. Number of replicates: {m}. Part: {part}")
            start = 0
            end = part
            sch_index = 0
            replica_number = 1
            ws_sch_index = 0

            while end <= makespan:
                self.log.debug(f"Step 2. Workcenter:{ws_id}. Interval [{start};{end}]")
                # check to see how many scheduled intervals fit in each makespan cut
                sch_end = schedule_list[sch_index]['end']
                while sch_index < len(schedule_list) and schedule_list[sch_index]['end'] <= end:
                    sch_index += 1

                if sch_index < len(schedule_list):
                    # we have at least one interval left
                    # TODO don't know if this may be an actual case
                    # we split the current interval

                    start_first = schedule_list[sch_index]['start']
                    end_first = end
                    start_second = end_first
                    new_schedule = schedule_list[sch_index].copy()
                    end_second = schedule_list[sch_index]['end']
                    schedule_list[sch_index]['end'] = end_first

                    if split_by_piece:
                        proposed_end = float(schedule_list[sch_index]['end'] - schedule_list[sch_index]['setup_time'])

                        # find closest: https://www.geeksforgeeks.org/multiple-of-x-closest-to-n/
                        def closestMultiple(n, x):
                            if x > n:
                                return x
                            z = (int)(x / 2)
                            n = n + z
                            n = n - (n % x)
                            return n

                        real_end = closestMultiple(proposed_end, float(schedule_list[sch_index]['one_product_time']))
                        if real_end > proposed_end:
                            real_end = real_end - float(schedule_list[sch_index]['one_product_time'])
                        real_end = real_end + schedule_list[sch_index]['setup_time']
                        schedule_list[sch_index]['end'] = real_end
                        start_second = real_end

                    new_schedule['start'] = start_second
                    new_schedule['end'] = new_schedule['end'] + new_schedule['setup_time']
                    sch_index += 1
                    schedule_list.insert(sch_index, new_schedule)
                    # update with setup time to all schedules after
                    for i in range(sch_index + 1, len(schedule_list)):
                        schedule_list[i]['start'] += new_schedule['setup_time']
                        schedule_list[i]['end'] += new_schedule['setup_time']

                    self.log.debug("Step 2. New schedule:")
                    print_schedule(schedule_list)

                self.log.debug(
                    f"Step 3. Schedule on Workcenter: {ws_id}, replica {replica_number}, station {ws_op['replicates'][replica_number - 1].name}]")

                while ws_sch_index < sch_index and schedule_list[ws_sch_index]['end'] <= end:
                    sch = schedule_list[ws_sch_index]

                    sch = schedule_list[ws_sch_index]
                    final_sch = {
                        'operation_code': sch['product_code'],
                        'start_time': sch['start'],
                        'end_time': sch['end'],
                        'proc_time': sch['product_assem_time'],
                        'setup_time': sch['setup_time'],
                        'ws_name': ws_op['replicates'][replica_number - 1].name,
                        'ws_id': ws_op['replicates'][replica_number - 1].id,
                    }
                    if sch['op_id'] not in final_scheduling_dict:
                        final_scheduling_dict[sch['op_id']] = []
                    final_scheduling_dict[sch['op_id']].append(final_sch)
                    self.log.debug(
                        f"Scheduled Operation {sch['op_id']}, product {sch['product_name']}-[{sch['start']};{sch['end']}]-setup_time:{sch['setup_time']}")

                    ws_sch_index += 1
                replica_number += 1

                start = end
                if end + part <= makespan:
                    end += part
                else:
                    end = makespan
                    break
        self.b_split_intervals = final_scheduling_dict
        self.b_split_proc_times = processing_times

    def b_sched(self, po_rowid=2000, po_rowid_list=[], scheduling_example_file=None):
        # forward pass in uncapacited way

        # get all operations

        op_list = []
        if len(po_rowid_list) > 0:
            for po_rowid in po_rowid_list:
                op_list.extend(self.data_source.operationDS.get_all_operations_for_product_command(po_rowid))
        else:
            op_list = self.data_source.operationDS.get_all_operations_for_product_command(po_rowid)

        # get all leafs
        leaves_operations = []
        parent_operation_ids = [op.parentoperationid for op in op_list]
        for op in op_list:
            if op.id not in parent_operation_ids:
                leaves_operations.append(op)

        # get all processing times (setup included)
        processing_times_dict = {}
        for pt in self.b_split_proc_times:
            processing_times_dict[pt['op_id']] = pt

        # compute early finish time (early start time) in forward pass
        op_info = {}
        op_info_capacitated = {}
        forward_operations = copy.deepcopy(leaves_operations)
        i = 0
        while i < len(forward_operations):
            operation = forward_operations[i]
            # additional check just to make sure each operation is processed once
            if operation.id not in op_info:
                op_info[operation.id] = {'operation_code': operation.productcode, 'early_start': 0}
                op_info_capacitated[operation.id] = {'operation_code': operation.productcode, 'early_start': 0}
            else:
                self.log.debug(f"Operation {operation.id} {operation.productcode} has already been processed")

            op_info[operation.id]['early_finish'] = op_info[operation.id]['early_start'] + \
                                                    processing_times_dict[operation.id]['product_assem_time']

            # get b_split_result info fo each operation
            b_split_list = self.b_split_intervals[operation.id]
            maxim_duration = max([sch['end_time'] - sch['start_time'] for sch in b_split_list])
            op_info_capacitated[operation.id]['early_finish'] = op_info_capacitated[operation.id][
                                                                    'early_start'] + maxim_duration

            # get parent
            # q_object_filter = Q(productid=operation.parentproductid)
            # result = opQueries.get_operations(q_object_filter)
            result = self.data_source.operationDS.get_by_operationid(operation.parentoperationid)
            if len(result) > 0:
                # parent_operation = opQueries.get_operations(q_object_filter)[0]
                parent_operation = self.data_source.operationDS.get_by_operationid(operation.parentoperationid)[0]
                if parent_operation.id in op_info:
                    max_early_start = max(op_info[parent_operation.id]['early_start'],
                                          op_info[operation.id]['early_finish'])
                    max_early_start_capacitated = max(op_info_capacitated[parent_operation.id]['early_start'],
                                                      op_info_capacitated[operation.id]['early_finish'])
                else:
                    max_early_start = op_info[operation.id]['early_finish']
                    max_early_start_capacitated = op_info_capacitated[operation.id]['early_finish']
                op_info[parent_operation.id] = {'operation_code': parent_operation.productcode,
                                                'early_start': max_early_start}
                op_info_capacitated[parent_operation.id] = {'operation_code': parent_operation.productcode,
                                                            'early_start': max_early_start_capacitated}
                forward_operations.append(parent_operation)

            i = i + 1

        # step 3 and 4
        # get all end nodes and update early finish time with the maximum
        # if po_rowid is not None:
        #     q_object_filter = Q(purchaseorderrowid=po_rowid) & Q(parentoperationid=None)
        # end_operations = list(opQueries.get_operations(q_object_filter))
        end_operations = self.data_source.operationDS.get_parent_operations(po_rowid)
        # print("-end_operations", end_operations)
        # print("-op_info_capacitated", op_info_capacitated)

        max_value = max([op_info_capacitated[op.id]['early_finish'] for op in end_operations])
        bk_op_info_capacitated = copy.deepcopy(op_info_capacitated)
        backward_operations = copy.deepcopy(end_operations)
        for op in end_operations:
            bk_op_info_capacitated[op.id]['early_finish'] = max_value
            bk_op_info_capacitated[op.id]['latest_finish'] = max_value

        i = 0
        scheduled_operations = {}
        # TODO-ia din tabela de mententa si populeaza dictionarul - ws_occupancy
        ws_occupancy = self.data_source.maintenanceDS.get_maintenance_intervals()
        while i < len(backward_operations):
            operation = backward_operations[i]
            if operation.id not in scheduled_operations:
                op_sch = {'operation_code': operation.productcode, 'start_time': None, 'end_time': None, 'ws_id': None,
                          'operation_id': operation.id,
                          'product_id': operation.productid,
                          'po_row_id': operation.purchaseorderrowid,
                          'po_id': operation.purchaseorderid
                          }
                scheduled_operations[operation.id] = op_sch
            else:
                op_sch = scheduled_operations[operation.id]

            if op_sch['end_time'] is None:
                op_sch['end_time'] = operation.deliverydate
            if op_sch['start_time'] is None:
                b_split_list = self.b_split_intervals[operation.id]
                min_start = None
                op_sch['capacitated'] = []
                for sch in b_split_list:
                    scheduled = {'start_time': None, 'end_time': None, 'ws_name': None, 'ws_id': None, 'proc_time':None, 'setup_time':None}
                    scheduled['ws_name'] = sch['ws_name']
                    scheduled['ws_id'] = sch['ws_id']
                    ws_id = sch['ws_id']
                    proc_time = sch['end_time'] - sch['start_time']
                    start_time = op_sch['end_time'] - datetime.timedelta(seconds=proc_time)
                    end_time = op_sch['end_time']

                    # find a free time for each machine -> similar to letsa
                    if ws_id not in ws_occupancy:
                        ws_occupancy[ws_id] = []
                        #ws_occupancy[ws_id].append([start_time, end_time])
                        # scheduled['ws_id'] = ws_id
                        # scheduled['start_time'] = start_time
                        # scheduled['end_time'] = end_time
                    else:
                        # from letsa
                        # check if current interval is available
                        for j, interval in reversed(list(enumerate(ws_occupancy[ws_id]))):
                            start = interval[0]
                            end = interval[1]
                            # plan here
                            if start_time <= end:
                                if start_time + datetime.timedelta(seconds=proc_time) > start:
                                    # move start_time
                                    start_time = start - datetime.timedelta(seconds=proc_time)
                                    end_time = start_time + datetime.timedelta(seconds=proc_time)

                    if start_time >= self.data_source.startTime:

                        ws_occupancy[ws_id].append([start_time, end_time])
                        scheduled['ws_id'] = ws_id
                        scheduled['start_time'] = start_time
                        scheduled['end_time'] = end_time
                        scheduled['proc_time'] = proc_time
                        if (min_start is None) or (min_start > scheduled['start_time']):
                            min_start = scheduled['start_time']
                    else:
                        execution_time = round(time.time() - self.alg_start_time, 4)
                        return (execution_time, "UNSATISFIED", -1)






                    op_sch['capacitated'].append(scheduled)
                op_sch['start_time'] = min_start

            # add children and update their end_time
            # q_object_filter = Q(parentproductid=operation.productid)
            # result = opQueries.get_operations(q_object_filter)
            result = self.data_source.operationDS.get_by_parent_operation(operation)

            if len(result) > 0:
                backward_operations.extend(result)
                for op in result:
                    child_sch = {'operation_code': op.productcode, 'start_time': None, 'end_time': None, 'ws_id': None,
                                 'operation_id': op.id,
                                 'product_id': op.productid,
                                 'po_row_id': op.purchaseorderrowid,
                                 'po_id': op.purchaseorderid
                                 }
                    child_sch['end_time'] = min_start
                    scheduled_operations[op.id] = child_sch

            i += 1

        scheduling_list = []
        for op_id in scheduled_operations:
            capacitated_list = scheduled_operations[op_id]['capacitated']
            for x in capacitated_list:
                x['operation_id'] = op_id
                x['operation_code'] = scheduled_operations[op_id]['operation_code']
                x['product_id'] = scheduled_operations[op_id]['product_id']
                x['po_row_id'] = scheduled_operations[op_id]['po_row_id']
                x['po_id'] = scheduled_operations[op_id]['po_id']
            scheduling_list.extend(capacitated_list)
            # print(scheduling_example_file, "scheduling_list",scheduling_list)
        if scheduling_example_file:
            with open(scheduling_example_file, 'w') as f:
                json.dump(scheduling_list, f, default=str)
        self.scheduling_list = scheduling_list
        self.ws_occupany = ws_occupancy

        min_date = min([op["start_time"] for op in scheduling_list])
        max_date = max([op["end_time"] for op in scheduling_list])

        execution_time = round(time.time() - self.alg_start_time, 4)
        return (execution_time, "SATISFIED", (max_date - min_date).total_seconds())

    def b_split_example(self, insert_op=True, insert_ps=True):
        if insert_op:
            operation = Op(2001, 'AA', 'A', po_row_id=2000, po_id=0, parent=None,
                           children_list=[],
                           quantity=3, parent_op=None,
                           delivery_date=datetime.datetime.now())
            op_db_parent = operation.insert_db()

            operation = Op(2002, 'BB', 'B', po_row_id=2000, po_id=0, parent=2001,
                           children_list=[],
                           quantity=30, parent_op=op_db_parent.id,
                           delivery_date=None)
            op_db_b = operation.insert_db()

            operation = Op(2003, 'CC', 'C', po_row_id=2000, po_id=0, parent=2001,
                           children_list=[],
                           quantity=30, parent_op=op_db_parent.id,
                           delivery_date=None)
            op_db_c = operation.insert_db()

            operation = Op(2004, 'DD', 'D', po_row_id=2000, po_id=0, parent=2001,
                           children_list=[],
                           quantity=30, parent_op=op_db_parent.id,
                           delivery_date=None)
            op_db_d = operation.insert_db()

            operation = Op(2005, 'EE.20', 'E.20', po_row_id=2000, po_id=0, parent=2002,
                           children_list=[],
                           quantity=30, parent_op=op_db_b.id,
                           delivery_date=None)
            op_db_e = operation.insert_db()

            operation = Op(2006, 'FF.20', 'F.20', po_row_id=2000, po_id=0, parent=2003,
                           children_list=[],
                           quantity=30, parent_op=op_db_c.id,
                           delivery_date=None)
            op_db_f = operation.insert_db()

            operation = Op(2007, 'G.20', 'G.20', po_row_id=2000, po_id=0, parent=2004,
                           children_list=[],
                           quantity=30, parent_op=op_db_d.id,
                           delivery_date=None)
            op_db_g = operation.insert_db()

            operation = Op(2008, 'EE.10', 'E.10', po_row_id=2000, po_id=0, parent=2005,
                           children_list=[],
                           quantity=30, parent_op=op_db_e.id,
                           delivery_date=None)
            op_db = operation.insert_db()

            operation = Op(2009, 'FF.10', 'F.10', po_row_id=2000, po_id=0, parent=2006,
                           children_list=[],
                           quantity=30, parent_op=op_db_f.id,
                           delivery_date=None)
            op_db = operation.insert_db()

            operation = Op(2010, 'GG.10', 'G.10', po_row_id=2000, po_id=0, parent=2007,
                           children_list=[],
                           quantity=30, parent_op=op_db_g.id,
                           delivery_date=None)
            op_db = operation.insert_db()

        if insert_ps:
            # st_1 = Station.objects.filter(id=1).using("scampml")[0]
            # st_2 = Station.objects.filter(id=2).using("scampml")[0]

            # create stations WS1 - 3 replicates, WS2 - 2 replicates, WS3 - 3 replicates, WS4-1 replicate
            st_1 = Station(id=5, name='WS11')
            st_1.save(using='scampml')
            st_2 = Station(id=6, name='WS12')
            st_2.save(using='scampml')
            st_3 = Station(id=7, name='WS13')
            st_3.save(using='scampml')

            st_4 = Station(id=8, name='WS21')
            st_4.save(using='scampml')
            st_5 = Station(id=9, name='WS22')
            st_5.save(using='scampml')

            st_6 = Station(id=10, name='WS31')
            st_6.save(using='scampml')
            st_7 = Station(id=11, name='WS32')
            st_7.save(using='scampml')

            st_8 = Station(id=12, name='WS41')
            st_8.save(using='scampml')

            # insert corresponding products and productstations
            p = Product(id=2001, code='AA', name='A')
            p.save(using='scampml')
            ps = ProductStation(id=28, productid=p, stationid=st_8,
                                cycletime=3, cyclequantity=1, setuptime=1, estimatedoee=1)
            ps.save(using='scampml')

            p = Product(id=2002, code='BB', name='B')
            p.save(using='scampml')
            ps = ProductStation(id=29, productid=p, stationid=st_6,
                                cycletime=8, cyclequantity=1, setuptime=2, estimatedoee=1)
            ps.save(using='scampml')

            ps = ProductStation(id=30, productid=p, stationid=st_7,
                                cycletime=8, cyclequantity=1, setuptime=2, estimatedoee=1)
            ps.save(using='scampml')

            p = Product(id=2003, code='CC', name='C')
            p.save(using='scampml')
            ps = ProductStation(id=31, productid=p, stationid=st_6,
                                cycletime=6, cyclequantity=1, setuptime=1, estimatedoee=1)
            ps.save(using='scampml')

            ps = ProductStation(id=32, productid=p, stationid=st_7,
                                cycletime=6, cyclequantity=1, setuptime=1, estimatedoee=1)
            ps.save(using='scampml')

            p = Product(id=2004, code='DD', name='D')
            p.save(using='scampml')
            ps = ProductStation(id=33, productid=p, stationid=st_6,
                                cycletime=9, cyclequantity=1, setuptime=2, estimatedoee=1)
            ps.save(using='scampml')
            ps = ProductStation(id=34, productid=p, stationid=st_7,
                                cycletime=9, cyclequantity=1, setuptime=2, estimatedoee=1)
            ps.save(using='scampml')

            p = Product(id=2005, code='EE.20', name='E.20')
            p.save(using='scampml')
            ps = ProductStation(id=35, productid=p, stationid=st_4,
                                cycletime=10, cyclequantity=1, setuptime=2, estimatedoee=1)
            ps.save(using='scampml')
            ps = ProductStation(id=36, productid=p, stationid=st_5,
                                cycletime=10, cyclequantity=1, setuptime=2, estimatedoee=1)
            ps.save(using='scampml')

            p = Product(id=2006, code='FF.20', name='F.20')
            p.save(using='scampml')
            ps = ProductStation(id=37, productid=p, stationid=st_4,
                                cycletime=8, cyclequantity=1, setuptime=1, estimatedoee=1)
            ps.save(using='scampml')
            ps = ProductStation(id=38, productid=p, stationid=st_5,
                                cycletime=8, cyclequantity=1, setuptime=1, estimatedoee=1)
            ps.save(using='scampml')

            p = Product(id=2007, code='GG.20', name='G.20')
            p.save(using='scampml')
            ps = ProductStation(id=39, productid=p, stationid=st_4,
                                cycletime=7, cyclequantity=1, setuptime=2, estimatedoee=1)
            ps.save(using='scampml')
            ps = ProductStation(id=40, productid=p, stationid=st_5,
                                cycletime=7, cyclequantity=1, setuptime=2, estimatedoee=1)
            ps.save(using='scampml')

            p = Product(id=2008, code='EE.10', name='E.10')
            p.save(using='scampml')
            ps = ProductStation(id=41, productid=p, stationid=st_1,
                                cycletime=5, cyclequantity=1, setuptime=2, estimatedoee=1)
            ps.save(using='scampml')
            ps = ProductStation(id=42, productid=p, stationid=st_2,
                                cycletime=5, cyclequantity=1, setuptime=2, estimatedoee=1)
            ps.save(using='scampml')
            ps = ProductStation(id=43, productid=p, stationid=st_3,
                                cycletime=5, cyclequantity=1, setuptime=2, estimatedoee=1)
            ps.save(using='scampml')

            p = Product(id=2009, code='FF.10', name='F.10')
            p.save(using='scampml')

            ps = ProductStation(id=44, productid=p, stationid=st_1,
                                cycletime=9, cyclequantity=1, setuptime=1, estimatedoee=1)
            ps.save(using='scampml')
            ps = ProductStation(id=45, productid=p, stationid=st_2,
                                cycletime=9, cyclequantity=1, setuptime=1, estimatedoee=1)
            ps.save(using='scampml')
            ps = ProductStation(id=46, productid=p, stationid=st_3,
                                cycletime=9, cyclequantity=1, setuptime=1, estimatedoee=1)
            ps.save(using='scampml')

            p = Product(id=2010, code='GG.10', name='G.10')
            p.save(using='scampml')

            ps = ProductStation(id=47, productid=p, stationid=st_1,
                                cycletime=10, cyclequantity=1, setuptime=2, estimatedoee=1)
            ps.save(using='scampml')
            ps = ProductStation(id=48, productid=p, stationid=st_2,
                                cycletime=10, cyclequantity=1, setuptime=2, estimatedoee=1)
            ps.save(using='scampml')
            ps = ProductStation(id=49, productid=p, stationid=st_3,
                                cycletime=10, cyclequantity=1, setuptime=2, estimatedoee=1)
            ps.save(using='scampml')

    def generate_dataframe(self):
        if self.scheduling_list != None:
            ws_list = []
            start_list = []
            end_list = []
            op_id_list = []
            op_code_list = []
            duration_list = []

            for sch_info in self.scheduling_list:
                ws_list.append(f"#{sch_info.get('ws_name', sch_info.get('ws_id'))}")
                start_list.append(sch_info['start_time'])
                end_list.append(sch_info['end_time'])
                op_id_list.append(sch_info['operation_id'])
                op_code_list.append(sch_info['operation_code'])
                duration_list.append((sch_info['end_time'] - sch_info['start_time']).total_seconds())  # / 60)

            scheduling_df = {'Workstation': ws_list,
                             'Start': start_list,
                             'End': end_list,
                             'Operation_Id': op_id_list,
                             'Operation_Code': op_code_list,
                             'Duration': duration_list
                             }
            return pd.DataFrame(scheduling_df)
        return pd.DataFrame()
    def generate_plot(self, dataframe=None, output_path=None):
        if output_path is None:
            output_path = self.PLOT_OUTPUT_DIR
        dataframe = self.generate_dataframe()
        if not dataframe.empty:
            fig = px.timeline(
                dataframe,
                x_start="Start",
                x_end="End",
                y="Workstation",
                hover_data=['Operation_Id', 'Duration'],
                color='Operation_Code',
                text="Operation_Code"
            )
            fig.update_yaxes(categoryorder='category ascending')

            # fig.update_yaxes(autorange="reversed")  # otherwise tasks are listed from the bottom up

            output_dir = Path(f"{output_path}/")
            output_dir.mkdir(parents=True, exist_ok=True)

            dataframe.to_csv(output_dir / f"{self.algorithm_name}_{self.data_source.sourceName}.csv", index=False)
            fig.write_html(output_dir / f"{self.algorithm_name}_{self.data_source.sourceName}.html",
                           include_plotlyjs=True)
            fig.write_image(output_dir / f"{self.algorithm_name}_{self.data_source.sourceName}.png", width=1020,
                            height=480)