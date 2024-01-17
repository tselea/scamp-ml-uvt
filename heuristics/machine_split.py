import datetime
import time
import logging
from z3 import Optimize, Int, Real, If, Implies, Or, And, sat, unsat, set_param, Sum
set_param('parallel.enable', True)
set_param('parallel.threads.max', 12)


class Machine_Split_Z3:

    class Item:
        """
        Helper class to collect information relate to workstation characteristic for a product
        """

        def __init__(self, setup_time, execution_time, estimatedoee, ws_id):
            """

            :param setup_time: the workstation setuptime is seconds
            :param execution_time: 1 product unit execution time / workstation
            :param estimatedoee: workstation OEE for the product
            :param ws_id: the workstation identifier
            """
            self.execution_time = execution_time
            self.setup_time = setup_time
            self.id = ws_id
            self.estimatedoee = estimatedoee

        def __repr__(self):
            return f"(wsId={self.id}; setupTIME={self.setup_time}; execution_time={self.execution_time} estimatedoee={self.estimatedoee})"

    def __init__(self, quantity, stations, start_time, completion_time, ws_occupancy, logging_level=logging.WARNING, variant="minim"):
        self.quantity = quantity
        self.stations = stations
        self.completion_time = completion_time.timestamp()
        self.ws_occupancy = ws_occupancy
        self.variant = variant
        self.start_time = start_time.timestamp()

        logging.basicConfig(level=logging_level)
        self.log = logging.getLogger("LETSA+Z3")

    def solve(self):

        m = len(self.stations)  # workstation numeber
        #print("self.execution_time:", self.completion_time, "quantity:", self.quantity, "stations:", self.stations)

        opt = Optimize()
        B = [Int("B_%s" % (w+1)) for w in range(m)]  # split quantity
        ET = [Int("ET_%s" % (w + 1)) for w in range(m)]  # execution time of b[i] conponents on workstation i
        ST = [Int("ST_%s" % (w + 1)) for w in range(m)]  # start time

        # constrains for Beans
        opt.add(Sum([B[w] for w in range(m)]) == self.quantity)
        opt.add([B[w] >= 0 for w in range(m)])
        opt.add([Implies(B[w] > 0, B[w] > self.quantity//4) for w in range(m)])  # 604645
        opt.add([B[w] <= self.quantity for w in range(m)])

        # constrains for execution time
        opt.add([Implies(B[w] == 0, ET[w] == 0) for w in range(m)])
        opt.add([Implies(B[w] > 0, ET[w] == (self.stations[w].setup_time + B[w] *
                                             self.stations[w].execution_time * self.stations[w].estimatedoee)) for w in range(m)])

        # constrains for start-time
        opt.add([ST[w] <= self.completion_time for w in range(m)])
        opt.add([ST[w] >= self.start_time for w in range(m)])
        opt.add([Implies(B[w] == 0, ST[w] == self.completion_time) for w in range(m)])
        opt.add([ST[w] + ET[w] <= self.completion_time for w in range(m)])

        # constraints for intervals where workstation is unavailable
        w = 0
        for station in self.stations:
            if station.id in self.ws_occupancy:
                list_occupancy = self.ws_occupancy[station.id]
                for occupancy in list_occupancy:
                    if occupancy[0].timestamp() < self.completion_time:
                        opt.add(Implies(B[w] > 0, Or(ST[w] + ET[w] < occupancy[0].timestamp(), ST[w] > occupancy[1].timestamp())))
            w += 1

        # balence machine load
        diff = []
        diff_count = 0
        for i in range(m-1):
            for j in range(i+1, m):
                var = Int("Diff_%s" % (i * m + j))
                diff.append(var)
                opt.add(Implies(ET[i] >= ET[j], var == ET[i] - ET[j]))
                opt.add(Implies(ET[i] < ET[j], var == ET[j] - ET[i]))
                diff_count += 1

        # https: // stackoverflow.com / questions / 25130271 / z3 - maximise - and -conflicts
        #opt.set('priority', 'box')
        #opt.minimize(sum([el for el in diff]))
        #opt.minimize(sum([ET[w] for w in range(m)]))
        if self.variant == "solverMinST":
            opt.maximize(sum([ST[w] for w in range(m)]))
        elif self.variant == "solverLoadBalacing":
            if len(diff) > 0:
               opt.minimize(sum([diff[d] for d in range(diff_count)]))
            # opt.minimize(sum([ET[w] for w in range(m)]))
            for w in range(m):
                opt.maximize(ST[w])
            # 8852
        else:
            v = Int("aux")
            opt.add(Or([v == ST[i] for i in range(m)]))  # v is an element in x)
            for i in range(m):
                opt.add(v <= ST[i])  # and it's the smallest
            for w in range(m):
                opt.maximize(ST[w])

        status = opt.check()

        quatity = []
        st = []
        t = []
        if status == sat:
            model = opt.model()

            for w in range(m):
                quatity.append(model[B[w]].as_long())
                # f = model[ST[w]].as_fraction()
                # st.append(f.numerator/f.denominator)
                # f = model[ET[w]].as_fraction()
                # t.append(f.numerator/f.denominator)
                st.append(model[ST[w]].as_long())
                t.append(model[ET[w]].as_long())
        else:
            print("UNSAT")
            # print(opt.sexpr())

        # with open("model", 'w') as fo:
        #     fo.write(opt.sexpr())
        # fo.close()
        # print("rezultat:", quatity, st, t)
        # for s in st:
        #     if s<=10: print(opt.sexpr())
        # self.log.debug(opt.sexpr())
        self.log.debug(f'quatity: {quatity}, start_time {st}, execution time {t}')
        return quatity, st, t


if __name__ == '__main__':
    # stations: [(wsId=3; setupTIME=360; execution_time=420 estimatedoee=1),
    #            (wsId=2; setupTIME=600; execution_time=540 estimatedoee=1),
    #            (wsId=4; setupTIME=480; execution_time=360 estimatedoee=1)]

    # [(wsId=2; setupTIME=360; execution_time=360 estimatedoee=1),
    #  (wsId=1; setupTIME=420; execution_time=420 estimatedoee=1),
    #  (wsId=5; setupTIME=540; execution_time=540 estimatedoee=1)]

    # stations = [Machine_Split_Z3.Item(360, 420, 1, 3), Machine_Split_Z3.Item(600, 540, 1, 2),
    #             Machine_Split_Z3.Item(480, 360, 1, 4)]

    stations = [Machine_Split_Z3.Item(360, 360, 1, 2), Machine_Split_Z3.Item(420, 420, 1, 1),
                Machine_Split_Z3.Item(540, 540, 1, 5)]

    # stations = [Machine_Split_Z3.Item(120,30,0.1,1), Machine_Split_Z3.Item(100, 35,0.1,2), Machine_Split_Z3.Item(573, 90000, 0.1,3)]
    a = Machine_Split_Z3(20, stations, datetime.datetime.fromtimestamp(100000000), {1: [[datetime.datetime.fromtimestamp(98345), datetime.datetime.fromtimestamp(98735)]]})
    # a = Machine_Split_Z3(100, stations, 100000, []) #([38, 33, 29], [98740, 98745, 98717], [1260, 1255, 1283])
    print(a.solve())
    print([98345, 98745])
