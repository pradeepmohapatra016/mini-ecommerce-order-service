import os
import sqlite3

DATABASE_NAME = os.getenv("DATABASE_PATH", "/app/data/orders.db")


def get_db_connection():
    os.makedirs(os.path.dirname(DATABASE_NAME), exist_ok=True)
    connection = sqlite3.connect(DATABASE_NAME)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    connection = get_db_connection()

    connection.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            total_price REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'CREATED'
        )
    """)

    connection.commit()
    connection.close()