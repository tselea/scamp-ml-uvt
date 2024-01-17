from db.models_uvt import Operation as DbOperation


# from db.models_uvt import Operationworkstation as DbOperationWS


class Operation(object):
    """
    Class that keeps information related to an production order
    """

    def __init__(self, product_id, product_code, product_name, po_row_id=None, po_id=None, parent=None,
                 children_list=None, quantity=None, parent_op=None, delivery_date=None):
        """
        :parameter product - product name
        :parameter parents_list - list containing references to direct parents nodes
        :parameter children_list - list containing references to direct child nodes
        :parameter quantity  - the numbers of products that have to be produced
        """
        self.product_id = product_id
        self.product_code = product_code
        self.product_name = product_name
        self.po_row_id = po_row_id
        self.po_id = po_id
        self.parent = parent
        self.children_list = children_list
        self.quantity = quantity
        self.stations_list = []
        self.parent_op = parent_op
        self.delivery_date = delivery_date

    def insert_db(self):
        # TODO update purchase order id, status not hardcoded
        o = DbOperation(purchaseorderrowid=self.po_row_id, purchaseorderid=self.po_id, productid=self.product_id,
                        quantity=self.quantity, status="N", productcode=self.product_code,
                        productname=self.product_name, parentproductid=self.parent, parentoperationid=self.parent_op,
                        deliverydate=self.delivery_date)
        o.save(using='scampml_uvt')
        return o


# class OperationWorkStation(object):
#
#     def __init__(self, operation_id, station_id, max_finish_time, product_assem_time):
#
#         self.operation_id = operation_id
#         self.station_id = station_id
#         self.max_finish_time = max_finish_time
#         self.product_assem_time = product_assem_time
#
#     def insert_db(self):
#
#         ows = DbOperationWS(operationid = self.operation_id, stationid = self.station_id, productassemtime=self.product_assem_time)
#         ows.save(using='scampml_uvt')
#         return ows

class ProductStation(object):
    """
    Class that stores information related to a product execution on a station
    """

    def __init__(self, setup_time, cycle_time):
        """
        :parameter setup_time - time in seconds used to configure the station to start producing the product
        :parameter cycle_time - time in seconds used to produce one product on the station
        :parameter estimated_start_time - time to start production for the coresponding order
        """
        self.setup_time = setup_time
        self.cycle_time = cycle_time
        self.estimated_start_time = None


class Workstation(object):
    """
    Class that stores information related to workstation status
    """

    def __init__(self):
        self.id = id
        self.unavailable_intervals = []
