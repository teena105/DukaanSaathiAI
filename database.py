import sqlite3

DATABASE = "dukaansaathi.db"


def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            stock REAL NOT NULL DEFAULT 0,
            unit TEXT NOT NULL DEFAULT 'kg',
            active INTEGER NOT NULL DEFAULT 1
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            customer_name TEXT,
            quantity REAL NOT NULL,
            unit_price REAL NOT NULL DEFAULT 0,
            total REAL NOT NULL,
            sale_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    """)

    sales_columns = [
        row["name"]
        for row in conn.execute("PRAGMA table_info(sales)").fetchall()
    ]

    if "customer_name" not in sales_columns:
        conn.execute(
            "ALTER TABLE sales ADD COLUMN customer_name TEXT"
        )

    if "unit_price" not in sales_columns:
        conn.execute(
            "ALTER TABLE sales ADD COLUMN unit_price REAL NOT NULL DEFAULT 0"
        )

    if "unit" not in sales_columns:
        conn.execute(
            "ALTER TABLE sales ADD COLUMN unit TEXT NOT NULL DEFAULT 'kg'"
        )

    product_columns = [
        row["name"]
        for row in conn.execute("PRAGMA table_info(products)").fetchall()
    ]

    if "unit" not in product_columns:
        conn.execute(
            "ALTER TABLE products ADD COLUMN unit TEXT NOT NULL DEFAULT 'kg'"
        )

    if "active" not in product_columns:
        conn.execute(
            "ALTER TABLE products ADD COLUMN active INTEGER NOT NULL DEFAULT 1"
        )

    conn.commit()
    conn.close()
