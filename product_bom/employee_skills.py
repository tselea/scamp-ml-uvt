from django.db.models import Q

from db.dao.skill import get_all_product_stations_skills, get_skilled_employees
from db.dao.team import get_team_schedule
from db.dao.workstation import get_all_stations, get_all_product_stations
import copy

import logging
logger = logging.getLogger(__name__)

class EmployeeSkillsManager():
    def __init__(self):
        pass

    def check_employee_skills(self, scheduling_list, ws_occupancy):

        skill_status = {}
        for operation in scheduling_list:
            req_productid = operation['product_id']
            req_stationid = operation['ws_id']

            start_operation = operation['start_time']
            end_operation = operation['end_time']
            logger.debug(f"Get product station info for {req_productid} and {req_stationid}")
            #for each operation get the corresponding ProductStation row (only one)
            q_objects = Q(productid=req_productid, stationid=req_stationid)
            product_station = get_all_product_stations(q_objects)[0]

            #for each product_station get the corresponding skill and employee req rows (one or more)
            q_object_filter = Q(productstationid=product_station.id)
            product_station_skills_list = get_all_product_stations_skills(q_object_filter)

            for ps_skill in product_station_skills_list:
                skillid = ps_skill.skillid
                employee_count = ps_skill.employeecount
                employee_max = ps_skill.employeecountmax
                #get the employees list with skill
                q_object_filter = Q(skillid=skillid)
                employees_list = get_skilled_employees(q_object_filter)
                nr_available_employees = 0
                for employee in employees_list:
                    #get the team schedule
                    team = employee.employeeid.teamid
                    team_id = team.id
                    q_object_filter = Q(teamid=team_id)
                    teams_schedule_list = get_team_schedule(q_object_filter)

                    #check overlapping intervals
                    for team_shift in teams_schedule_list:
                        shift_start = team_shift.shiftstart
                        shift_end = team_shift.shiftend

                        #TODO check if this constraint is valid for scheduling interval
                        if (start_operation>= shift_start) and (end_operation<=shift_end):
                            nr_available_employees+=1
                if skillid not in skill_status:
                    skill_status[skillid] = {}
                if nr_available_employees>= employee_count:
                    skill_status[skillid][operation['operation_id']] = 'Covered'
                else:
                    skill_status[skillid][operation['operation_id']] = f'Required {employee_count-nr_available_employees} employee to cover the interval {start_operation} - {end_operation}, skill {skillid}, for operation {operation["operation_id"]}.'



        return skill_status

    def check_employee_skills_v2(self, scheduling_list, ws_occupancy):


        employee_dict = {}
        skill_status = {}
        for operation in scheduling_list:
            req_productid = operation['product_id']
            req_stationid = operation['ws_id']

            start_operation = operation['start_time']
            end_operation = operation['end_time']
            #for each operation get the corresponding ProductStation row (only one)
            q_objects = Q(productid=req_productid, stationid=req_stationid)
            product_station = get_all_product_stations(q_objects)[0]

            #for each product_station get the corresponding skill and employee req rows (one or more)
            q_object_filter = Q(productstationid=product_station.id)
            product_station_skills_list = get_all_product_stations_skills(q_object_filter)

            for ps_skill in product_station_skills_list:
                skillid = ps_skill.skillid
                employee_count = ps_skill.employeecount
                employee_max = ps_skill.employeecountmax
                #get the employees list with skill
                q_object_filter = Q(skillid=skillid)
                employees_list = get_skilled_employees(q_object_filter)
                nr_available_employees = 0
                selected_employees = []
                for employee in employees_list:
                    #get the team schedule
                    team = employee.employeeid.teamid
                    team_id = team.id
                    q_object_filter = Q(teamid=team_id)
                    teams_schedule_list = get_team_schedule(q_object_filter)

                    selected_employees.append(employee.id)

                    #check overlapping intervals
                    for team_shift in teams_schedule_list:
                        shift_start = team_shift.shiftstart
                        shift_end = team_shift.shiftend
                        if employee.id not in employee_dict:
                            #load shift for each employee
                            employee_dict[employee.id] = {}
                            employee_dict[employee.id]['shift'] = (shift_start, shift_end)
                            employee_dict[employee.id]['free'] = [[shift_start, shift_end]]

                        #TODO check if this constraint is valid for scheduling interval
                        # if (start_operation>= shift_start) and (end_operation<=shift_end):
                        #     nr_available_employees+=1

                #select only the employees with skill
                selected_employees_dict = {k: employee_dict[k] for k in selected_employees if k in employee_dict}
                #basic assignment
                sorted_employees = sorted(selected_employees_dict.keys(), key=lambda x: selected_employees_dict[x]['free'][0][0])

                #cover the scheduled inverval in shifts
                start_time = start_operation
                end_time = end_operation

                for employee_id in sorted_employees:
                    free_inverval_list = employee_dict[employee_id]['free']
                    for idx,i in enumerate(free_inverval_list):
                        #case 1 the scheduled interval is fully contained
                        if start_time>=i[0] and end_time<=i[1]:
                            #select employee
                            employee_count-=1



                            #block employee
                            new_free_intervals = copy.deepcopy(free_inverval_list)
                            new_free_intervals[idx][1] = start_time
                            new_free_intervals.insert(idx+1,(end_time, i[1]))
                            employee_dict[employee_id]['free'] = new_free_intervals



                            break
                    if employee_count ==0:
                        break







                if skillid not in skill_status:
                    skill_status[skillid] = {}
                if employee_count == 0:
                    skill_status[skillid][operation['operation_id']] = 'Covered'
                else:
                    skill_status[skillid][operation['operation_id']] = f'Required {employee_count} employee to cover the interval {start_operation} - {end_operation}, skill {skillid}, for operation {operation["operation_id"]}.'



        return skill_status







