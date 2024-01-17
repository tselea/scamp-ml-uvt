import datetime

import pandas as pd


class BatchSplittingTemplate:

    def _generate_dataframe_batch_splitting(self):
        data = []
        if self.solution and self.solution["Status"] != "UNSATISFIED":
            n = self.solution['n']
            m = self.solution['m']
            start_time = self.solution['planificationStartTime']

            for i in range(n):
                for ws in range(m):
                    if self.solution["workstationAssignment"][i][ws] == 1:
                        data.append(dict(ID=self.solution['operationIDs'][i],
                                         Start=(start_time + datetime.timedelta(seconds=self.solution['startTime'][i][ws])),
                                         Finish=(start_time + datetime.timedelta(seconds=self.solution['completeTime'][i][ws])),
                                         Duration=round((self.solution['completeTime'][i][ws] - self.solution['startTime'][i][ws]) / 60, 2),
                                         Workstation=self.solution["workstationNames"][ws],
                                         ProductCode=self.solution["operationProductCode"][i],
                                         Quantity=f"{self.solution['Batch'][i][ws]}/{self.solution['operationProductQuantity'][i]}",
                                         quantity=self.solution['Batch'][i][ws]))
            return pd.DataFrame(data)
        return pd.DataFrame()
