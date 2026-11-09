
import os
import requests
from flask import Flask, request, jsonify

from database import get_db_connection, initialize_database
from models import order_to_dict

app = Flask(__name__)

# Product Service URL
PRODUCT_SERVICE_URL = os.getenv(
    "PRODUCT_SERVICE_URL",
    "http://172.19.92.166:30001"
)

initialize_database()


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "service": "order-service",
        "status": "healthy"
    })


# Create a new order
@app.route("/orders", methods=["POST"])
def create_order():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "Valid JSON object required"}), 400

    product_id = data.get("product_id")
    quantity = data.get("quantity")

    if type(product_id) is not int or product_id <= 0:
        return jsonify({"error": "Invalid product_id"}), 400

    if type(quantity) is not int or quantity <= 0:
        return jsonify({"error": "Invalid quantity"}), 400

    # Verify product through Product Service
    try:
        response = requests.get(
            f"{PRODUCT_SERVICE_URL}/products/{product_id}",
            timeout=5
        )
    except requests.RequestException:
        return jsonify({"error": "Product Service unavailable"}), 503

    if response.status_code == 404:
        return jsonify({"error": "Product not found"}), 404

    if response.status_code != 200:
        return jsonify({"error": "Unable to verify product"}), 502

    product = response.json()

    
    # Get product details from Product Service
    try:
        response = requests.get(
            f"{PRODUCT_SERVICE_URL}/products/{product_id}",
            timeout=5
        )
    except requests.RequestException:
        return jsonify({"error": "Product Service unavailable"}), 503

    if response.status_code == 404:
        return jsonify({"error": "Product not found"}), 404

    if response.status_code != 200:
        return jsonify({"error": "Unable to retrieve product"}), 502

    product = response.json()

    # Reserve stock through Product Service
    try:
        reservation = requests.post(
            f"{PRODUCT_SERVICE_URL}/products/{product_id}/reserve",
            json={"quantity": quantity},
            timeout=5
        )
    except requests.RequestException:
        return jsonify({"error": "Stock reservation failed"}), 503

    if reservation.status_code == 404:
        return jsonify({"error": "Product not found"}), 404

    if reservation.status_code == 409:
        return jsonify(reservation.json()), 409

    if reservation.status_code != 200:
        return jsonify({"error": "Unable to reserve stock"}), 502

    unit_price = product["price"]
    total_price = round(unit_price * quantity, 2)


    # Save order in the separate Order database
    connection = get_db_connection()

    cursor = connection.execute(
        """INSERT INTO orders
           (product_id, quantity, unit_price, total_price, status)
           VALUES (?, ?, ?, ?, ?)""",
        (product_id, quantity, unit_price, total_price, "CREATED")
    )

    connection.commit()
    order_id = cursor.lastrowid
    connection.close()

    return jsonify({
        "message": "Order created successfully",
        "order_id": order_id,
        "product_id": product_id,
        "quantity": quantity,
        "unit_price": unit_price,
        "total_price": total_price,
        "status": "CREATED"
    }), 201


# Retrieve all orders
@app.route("/orders", methods=["GET"])
def get_orders():
    connection = get_db_connection()
    orders = connection.execute(
        "SELECT * FROM orders ORDER BY id"
    ).fetchall()
    connection.close()

    return jsonify([order_to_dict(order) for order in orders])


# Retrieve one order
@app.route("/orders/<int:order_id>", methods=["GET"])
def get_order(order_id):
    connection = get_db_connection()

    order = connection.execute(
        "SELECT * FROM orders WHERE id = ?",
        (order_id,)
    ).fetchone()

    connection.close()

    if order is None:
        return jsonify({"error": "Order not found"}), 404

    return jsonify(order_to_dict(order))


# Update order status
@app.route("/orders/<int:order_id>/status", methods=["PUT"])
def update_order_status(order_id):
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "Valid JSON object required"}), 400

    status = data.get("status")
    allowed_statuses = ["CONFIRMED", "SHIPPED", "DELIVERED"]

    if status not in allowed_statuses:
        return jsonify({
            "error": "Invalid status",
            "allowed_statuses": allowed_statuses
        }), 400

    connection = get_db_connection()

    cursor = connection.execute(
        "UPDATE orders SET status = ? WHERE id = ?",
        (status, order_id)
    )

    connection.commit()
    updated = cursor.rowcount
    connection.close()

    if updated == 0:
        return jsonify({"error": "Order not found"}), 404

    return jsonify({
        "message": "Order status updated successfully",
        "order_id": order_id,
        "status": status
    })


# Delete an order

@app.route("/orders/<int:order_id>", methods=["DELETE"])
def delete_order(order_id):
    connection = get_db_connection()

    order = connection.execute(
        "SELECT * FROM orders WHERE id = ?",
        (order_id,)
    ).fetchone()

    if order is None:
        connection.close()
        return jsonify({"error": "Order not found"}), 404

    if order["status"] in ["SHIPPED", "DELIVERED"]:
        connection.close()
        return jsonify({
            "error": "Cannot cancel shipped or delivered orders"
        }), 409

    if order["status"] == "CANCELLED":
        connection.close()
        return jsonify({"error": "Order already cancelled"}), 409

    # Restore product stock
    try:
        response = requests.post(
            f"{PRODUCT_SERVICE_URL}/products/{order['product_id']}/restore",
            json={"quantity": order["quantity"]},
            timeout=5
        )
    except requests.RequestException:
        connection.close()
        return jsonify({"error": "Product Service unavailable"}), 503

    if response.status_code != 200:
        connection.close()
        return jsonify({
            "error": "Unable to restore product stock",
            "details": response.json()
        }), 502

    # Mark order as cancelled
    connection.execute(
        "UPDATE orders SET status = ? WHERE id = ?",
        ("CANCELLED", order_id)
    )

    connection.commit()
    connection.close()

    return jsonify({
        "message": "Order cancelled successfully",
        "order_id": order_id,
        "restored_quantity": order["quantity"],
        "status": "CANCELLED"
    })



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002)
