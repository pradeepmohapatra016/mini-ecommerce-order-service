
def order_to_dict(order):
    return {
        "id": order["id"],
        "product_id": order["product_id"],
        "quantity": order["quantity"],
        "unit_price": order["unit_price"],
        "total_price": order["total_price"],
        "status": order["status"]
    }
