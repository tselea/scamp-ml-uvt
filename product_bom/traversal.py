import datetime
import logging

import db.dao.order as orderQueries
import db.dao.product as productQueries
import db.dao.workstation as wsQueries
from db.models import *
from db.models_uvt import Operation as DBOp  # Operationworkstation as DBOpWS,
from product_bom.operation import Operation  # , OperationWorkStation

logger = logging.getLogger(__name__)

def basic_traversal():
    product_dict = {}
    po_output_dict = {"purchase_order": []}

    # get all orders
    po_list = orderQueries.get_all_purchase_orders()
    for po in po_list:
        print(f"Processing PO id {po.number}")
        po_output_dict["purchase_order"].append({"id": po.id, "number": po.number, "rows": []})
        # for each order get po rows
        po_row_list = PurchaseOrderRow.objects.filter(purchaseorderid=po.id).using("scampml_uvt_eta2u")
        for po_row in po_row_list:
            print(f"Processing PO row id {po_row.id}")
            po_output_dict["purchase_order"][-1]['rows'].append({"id": po_row.id, "process_products": []})
            product_list = []
            start_product = po_row.productid
            product_list.append((start_product, round(float(po_row.quantity), 2)))
            vis_products = [start_product.id]

            index = 0
            while index < len(product_list):
                current_product = product_list[index][0]
                current_quantity = product_list[index][1]
                # get the adjacent products
                adj_product_list = productQueries.get_product_direct_subcomponents(current_product.id)
                for adj_prod in adj_product_list:
                    if adj_prod.materialid.id not in vis_products:
                        product_list.append(
                            (adj_prod.materialid, round(current_quantity * float(adj_prod.materialquantity), 2)))
                        vis_products.append(adj_prod.materialid.id)

                index += 1
            process_products = po_output_dict["purchase_order"][-1]['rows'][-1]['process_products']
            for p, q in product_list:
                process_products.append({"id": p.id, "code": p.code, "name": p.name, "quantity": q})

    print(po_output_dict)

    import json
    with open('../files/basic_traversal.json', 'w') as f:
        json.dump(po_output_dict, f, indent=4)


def build_product_BOM(product_id, product_code, product_name, quantity, delivery_date, po_row_id, po_id) -> list:
    operations = []

    products_to_expand = [{"id": product_id, "code": product_code, "name": product_name, "quantity": quantity,
                           "delivery_date": delivery_date, "parent": None, "parent_op": None}]

    while len(products_to_expand) > 0:

        logger.debug(f'Products to expand list:{[(x["id"], x["code"], x["parent"]) for x in products_to_expand]}')
        current_product = products_to_expand.pop(0)

        product = Product.objects.filter(id=current_product["id"]).using("scampml_uvt_eta2u")[0]

        operation = Operation(product.id, product.code, product.name, po_id=po_id, po_row_id=po_row_id,
                              parent=current_product['parent'], children_list=[],
                              quantity=current_product["quantity"], parent_op=current_product['parent_op'],
                              delivery_date=current_product["delivery_date"])
        operations.append(operation)
        op_db = operation.insert_db()

        # get workstation list
        ws_list = wsQueries.get_product_stations(product.id)
        max_product_assem_time = -1

        for ws in ws_list:
            # TODO compute product assem time if cylce quantity is not 1
            product_assem_time = (ws.estimatedoee * ws.cycletime) * current_product['quantity'] + ws.setuptime
            if product_assem_time > max_product_assem_time:
                max_product_assem_time = product_assem_time

            # TODO add tzinfo to datetime
            end_time = current_product['delivery_date'] - datetime.timedelta(seconds=float(product_assem_time))
            # operation_ws = OperationWorkStation(op_db,ws.stationid.id,end_time, product_assem_time)
            # operation_ws.insert_db()

        end_time_children = current_product['delivery_date'] - datetime.timedelta(seconds=float(max_product_assem_time))
        children = productQueries.get_product_direct_subcomponents(product.id)
        for child in children:
            if child.materialid.israw:
                continue
            child_dict = {"id": child.materialid.id, "code": child.materialid.code, "name": child.materialid.name,
                          "quantity": child.materialquantity * current_product['quantity'],
                          "delivery_date": end_time_children, "parent": product.id, "parent_op": op_db.id}
            products_to_expand.append(child_dict)
    return operations


def products_BOM_PO(delete_all=False) -> None:
    po_output_dict = {"purchase_order": []}

    if delete_all:
        # DBOpWS.objects.all().using("scampml_uvt").delete()
        DBOp.objects.all().using("scampml_uvt").delete()

    # get all purchase orders
    po_list = orderQueries.get_all_purchase_orders()
    for po in po_list:
        print(f"Processing PO id {po.number}")
        delivery_date = po.deliverydate
        # for each order get po rows
        po_row_list = PurchaseOrderRow.objects.filter(purchaseorderid=po.id).using("scampml_uvt_eta2u")
        for po_row in po_row_list:
            print(f"Processing PO row id {po_row.id}")
            quantity = po_row.quantity
            # build product BOM for each purchare order row
            product_id = po_row.productid.id
            product_code = po_row.productid.code
            product_name = po_row.productid.name
            po_row_id = po_row.id
            print(product_id, product_code, product_name, quantity, delivery_date)
            build_product_BOM(product_id, product_code, product_name, quantity, delivery_date, po_row_id)
