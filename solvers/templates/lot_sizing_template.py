import datetime

import pandas as pd


class LotSizingTemplate():

    def _generate_dataframe_lot_sizing(self):
        data = []
        if self.solution and self.solution["Status"] != "UNSATISFIED":
            n = self.solution['n']
            start_time = self.solution['planificationStartTime']

            for i in range(n):
                ws = self.solution["workstationIDs"].index(self.solution["workstationAssignment"][i])
                data.append(dict(ID=self.solution['operationIDs'][i],
                                 Start=(start_time + datetime.timedelta(seconds=self.solution['startTime'][i])),
                                 Finish=(start_time + datetime.timedelta(
                                     seconds=self.solution['completeTime'][i])),
                                 Duration=round((self.solution['completeTime'][i] - self.solution['startTime'][i]) / 60,
                                                2), Workstation=self.solution["workstationNames"][ws],
                                 ProductCode=self.solution["operationProductCode"][i],
                                 Quantity=self.solution["operationProductQuantity"][i]))
            return pd.DataFrame(data)
        return pd.DataFrame()
