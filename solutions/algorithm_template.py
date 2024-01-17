import datetime
import logging

from django.utils import timezone
from django.utils.timezone import make_aware

#from SCAMPJSSP.solution import Solution, SolutionFactory
from db.dao.scheduling_result import SchedulingSummary, SchedulingDetailed

from pathlib import Path

import pandas as pd
import plotly.express as px

class AlgorithmTemplate():
    PLOT_OUTPUT_DIR = 'visualize/templates/plots'

    def __init__(self, data_source=None, algorithm_name=None, logging_level=logging.WARNING):
        """
        Constructor
        :param data_source: the datasource to use JSON or DB
        """
        self.data_source = data_source
        self.algorithm_name = algorithm_name

        logging.basicConfig(level=logging_level)
        print("algorithm_name", self.algorithm_name)
        self.log = logging.getLogger(self.algorithm_name)
        self.solver = None

    def solve(self, po_rowid=None, po_rowid_list=[]):
        """
        Method used to start the sheduling algorithm
        :return: makespan
        """
        pass

    def generate_dataframe(self):
        """
          :param scheduling_file:
          :return:
        """
        pass

    # def generate_plot(self, dataframe=None, output_path=None):
    #     """
    #     :param dataframe: the data source for gantt diagram
    #     :param output_file:
    #     :return:
    #     """
    #     pass

    def save_scheduling_result(self):
        issue_date = timezone.now()
        start_date = min(self.scheduling_list, key=lambda x: x['start_time'])['start_time']
        completion_date = max(self.scheduling_list, key=lambda x: x['end_time'])['end_time']

        start_date = make_aware(start_date)
        completion_date = make_aware(completion_date)

        scheduling_summary = SchedulingSummary(alg_name=self.algorithm_name, issue_date=issue_date,
                                               sch_start_date=start_date, sch_complete_date=completion_date)
        sched_summ = scheduling_summary.insert_db()

        for sch in self.scheduling_list:
            scheduling_detailed = SchedulingDetailed(scheduling_id=sched_summ, po_id=sch.get('po_id'),
                                                     po_row_id=sch.get('po_row_id'),
                                                     alg_name=self.algorithm_name,
                                                     operation_id=sch.get('operation_id'),
                                                     start_time=sch.get('start_time'),
                                                     completion_time=sch.get('end_time'),
                                                     product_id=sch.get('product_id'),
                                                     station_id=sch.get('ws_id')
                                                     )
            scheduling_detailed.insert_db()

    def filter_maintenance(self):
        """
        Method to filter Maintenance intervals for ws_occupancy list.
        Update maintenance attribute with the maintenance intervals included in the scheduling timeline.
        """

        #get all maintenance intervals
        all_maintenance = self.data_source.maintenanceDS.get_maintenance_intervals()
        # ws_occupancy[9].append([datetime.datetime(2022,11,28), datetime.datetime(2022, 11, 29, 18, 30)])

        #get start and end date of the entire scheduling
        min_start_date = None
        max_end_date = None

        # if isinstance(self.scheduling_list, Solution):
        #     self.scheduling_list = self.convert_solution_to_scheduling_list(self.scheduling_list)

        print("scheduling list: ", self.scheduling_list)

        if len(self.scheduling_list) < 1:
            self.maintenance = {}
            return

        for scheduling in self.scheduling_list:
            start_time = scheduling['start_time']
            end_time = scheduling['end_time']
            if (not min_start_date) or (min_start_date> start_time):
                min_start_date = start_time
            if (not max_end_date) or (max_end_date < end_time):
                max_end_date = end_time

        scheduled_start = min_start_date.timestamp()
        scheduled_end = max_end_date.timestamp()

        selected_maintenance = {}
        for ws, maintenance in all_maintenance.items():
            if ws in self.ws_occupancy:
                scheduled_intervals = self.ws_occupancy[ws]
                m_index = []
                for m in maintenance:
                    if m in scheduled_intervals:
                        id = scheduled_intervals.index(m)
                        m_index.append(id)

                        #check for overlap
                        m_start = m[0].timestamp()
                        m_end = m[1].timestamp()

                        overlap = min(m_end, scheduled_end) - max(m_start, scheduled_start)
                        if overlap >=0:
                            if ws not in selected_maintenance:
                                selected_maintenance[ws] = []
                            selected_maintenance[ws].append(m)

                #remove all maintenance from ws_occupancy
                for i in sorted(m_index, reverse=True):
                    del self.ws_occupancy[ws][i]
                    if len(self.ws_occupancy[ws])<1:
                        del self.ws_occupancy[ws]

        self.maintenance = selected_maintenance

    def generate_dataframe(self):
        def format_makespan(time):
            days = time // (24 * 3600)
            time = time % (24 * 3600)
            hours = time // 3600
            time %= 3600
            minutes = time // 60
            time %= 60
            seconds = time
            return ("%dd:%dh:%dm:%ds" % (days, hours, minutes, seconds))

        if self.scheduling_list != None:
            ws_list = []
            start_list = []
            end_list = []
            op_id_list = []
            op_code_list = []
            duration_list = []
            quantity_list = []

            for sch_info in self.scheduling_list:
                ws_list.append(f"#{sch_info.get('ws_name', sch_info.get('ws_id'))}")
                start_list.append(sch_info['start_time'])
                end_list.append(sch_info['end_time'])
                op_id_list.append(sch_info['operation_id'])
                op_code_list.append(sch_info['operation_code'])
                duration_list.append(format_makespan((sch_info['end_time'] - sch_info['start_time']).total_seconds()))  # / 60)
                quantity_list.append(sch_info['quantity'])

            for maintenance in self.data_source.maintenanceDS.get_maintenances():
                ws_list.append(f"#{self.data_source.stationsDS.get_by_id(maintenance.stationid.id)}")
                start_list.append(maintenance.maintenancestart)
                end_list.append(maintenance.maintenancestop)
                op_id_list.append(maintenance.id)
                op_code_list.append("MAINT.")
                duration_list.append(format_makespan((maintenance.maintenancestop - maintenance.maintenancestart).total_seconds()))  # / 60)
                quantity_list.append("-")

            scheduling_df = {'Workstation': ws_list,
                             'Start': start_list,
                             'End': end_list,
                             'Operation_Id': op_id_list,
                             'Operation_Code': op_code_list,
                             'Duration': duration_list,
                             'Quantity': quantity_list
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

    # def convert_solution_to_scheduling_list(self, solution):
    #    return self.solver.convert_solution_to_scheduling_list(solution)

    def strtobool(self, val):
        """Convert a string representation of truth to true (1) or false (0).
        True values are 'y', 'yes', 't', 'true', 'on', and '1'; false values
        are 'n', 'no', 'f', 'false', 'off', and '0'.  Raises ValueError if
        'val' is anything else.
        """
        val = val.lower()
        if val in ('y', 'yes', 't', 'true', 'on', '1'):
            return 1
        elif val in ('n', 'no', 'f', 'false', 'off', '0'):
            return 0
        else:
            raise ValueError("invalid truth value %r" % (val,))