import logging

from django.db.models import Q

import db.dao.stocks as StockDB
from db.models_uvt import Operation
import db.dao.product as ProductDB

logger = logging.getLogger(__name__)

class StockManager():

    def __init__(self):
        pass

    def load_stocks(self):
        #load stocks from db table
        stocks_list = StockDB.get_stocks()
        self.stocks_data = {}
        for st in stocks_list:
            self.stocks_data[st.productid.id] = st.quantity

    def load_aquisitions(self):
        # load stocks aquisitions from db table
        stocks_list = StockDB.get_stocks_aquisition()
        self.stock_aq = {}
        for st in stocks_list:
            if st.productid.id not in self.stock_aq:
                self.stock_aq[st.productid.id] = []
            self.stock_aq[st.productid.id].append ((st.aquisitiontime, float(st.quantity)))

        #sort by aquisition date
        for product in self.stock_aq:
            self.stock_aq[product] = sorted(self.stock_aq[product], key=lambda x: x[0])

    def check_stock_availability(self, po_rowid=None, po_rowid_list=[] ):
        #prepare po_rowid_list
        if len(po_rowid_list)<1:
            if po_rowid:
                po_rowid_list = [po_rowid]
            else:
                #get all po_rowids from Operations table
                po_rowid_list = [x['purchaseorderrowid'] for x in list(Operation.objects.values('purchaseorderrowid').using('scampml_uvt'))]


        #get all product ids
        operation_list = []
        for po_rowid in po_rowid_list:
            operation_list.extend(list(Operation.objects.filter(Q(purchaseorderrowid=po_rowid)).using(
                'scampml_uvt')))

        logger.debug(f"We considered the followig po_rowids {po_rowid_list}")
        logger.debug(f"All the operations considered are  {operation_list}")

        product_demand = {}
        raw_product_operations = []
        print (operation_list)
        for operation in operation_list:
            #check if product isRaw
            product = ProductDB.get_product(operation.productid)[0]
            print(product.israw)
            if operation.productid not in product_demand:
                product_demand[operation.productid] = operation.quantity
            else:
                product_demand[operation.productid]+=operation.quantity

        #check if stock exists
        stock_status = {}
        in_stock = True
        for product, demand in product_demand.items():
            if product not in self.stocks_data:
                in_stock = False
                stock_status[product] = 'Not in stock'
                continue
                #raise Exception(f'Stock is not provided for product id {product}. Please update the Stock Table.')
            product_stock = self.stocks_data[product]
            if product_stock<demand:
                in_stock = False
                stock_status[product] = 'Not in stock'
            else:
                stock_status[product] = 'In stock'


        return in_stock, stock_status

    def check_stock_aquisition(self, scheduling_list):
        #create demand info
        demand_dict = {}
        for operation in scheduling_list:
            if operation['product_id'] not in demand_dict:
                demand_dict[operation['product_id']] = {'total':0, 'detailed':[]}
            demand_dict[operation['product_id']]['detailed'].append((operation['start_time'], operation['quantity']))
            demand_dict[operation['product_id']]['total']+=operation['quantity']

        #sort demand lists by
        for product in demand_dict:
            demand_dict[product]['detailed'] = sorted( demand_dict[product]['detailed'], key=lambda x: x[0])

        #check stocks
        stock_status = {}
        for product, info in demand_dict.items():
            #1. entire stock is available for a product
            total_product = info['total']
            product_stock = self.stocks_data[product]
            if product_stock>= total_product:
                stock_status[product] = 'In stock'
                continue
            future_stock = product_stock
            i = 0
            stock_status[product] = []
            #2. check stock aquisiton for each date
            for demand in info['detailed']:
                #check if current demand is in stock
                i=0 #flavia nu trebie aici
                if demand[1]<= product_stock:
                    stock_status[product].append({'required_quantity': demand[1], 'stock_status': 'In stock'})
                    continue
                #find the first aqusisiton date later than start
                if product not in self.stock_aq:
                    aq_date = demand[0]  #add by flavia????nu stiu daca  e ce trebuie
                    stock_status[product].append({'required_quantity': demand[1], 'stock_status': 'Update stock', 'deadline':aq_date,'missing_quantity':demand[1]})
                    print(
                        f'Stock is not enough for product id {product}, until scheduling start {aq_date}. Please update the Stock.')
                    continue
                print('stoc: product', product, product in self.stock_aq, len(self.stock_aq[product]),i)
                aq_date = self.stock_aq[product][i][0]
                aq_stock = self.stock_aq[product][i][1]
                while aq_date < demand[0]:
                    future_stock += aq_stock
                    i += 1
                    if i<len(self.stock_aq[product]):
                        aq_date = self.stock_aq[product][i][0]
                        aq_stock = self.stock_aq[product][i][1]
                    else:
                        break

                if demand[1] <= future_stock:
                    stock_status[product].append({'required_quantity': demand[1], 'stock_status': 'In aquisiton stock'} )

                    future_stock -= demand[1]
                else:
                    stock_status[product].append({'required_quantity': demand[1], 'stock_status': 'Update stock', 'deadline':aq_date,'missing_quantity':demand[1]-future_stock})

                    print(f'Stock is not enough for product id {product}, until scheduling start {aq_date}. Please update the Stock.')

        return stock_status




    def update_stocks(self, scheduling_list):

        #update stocks according to scheduling
        for operation in scheduling_list:
            product_id = operation['product_id']
            quantity = operation['quantity']

            self.stocks_data[product_id]-=quantity
