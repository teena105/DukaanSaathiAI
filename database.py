"""Database helpers for a single-shop app on SQLite or hosted PostgreSQL."""

import os
import re
import sqlite3


DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
DATABASE = os.getenv("DUKAANSAATHI_DATABASE_PATH") or (
    "/tmp/dukaansaathi.db"
    if os.getenv("VERCEL")
    else os.path.join(os.path.dirname(__file__), "dukaansaathi.db")
)


class HybridRow:
    """Support both row['column'] and row[0], as sqlite3.Row does."""

    def __init__(self, columns, values):
        self._values = tuple(values)
        self._columns = dict(zip(columns, self._values))

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return self._columns[key]


def hybrid_row_factory(cursor):
    columns = [column.name for column in cursor.description or ()]

    def make_row(values):
        return HybridRow(columns, values)

    return make_row


class PostgresConnection:
    """Small adapter that keeps the app's existing qmark SQL portable."""

    def __init__(self, connection):
        self._connection = connection

    def execute(self, statement, parameters=()):
        return self._connection.execute(re.sub(r"\?", "%s", statement), parameters)

    def commit(self):
        self._connection.commit()

    def rollback(self):
        self._connection.rollback()

    def close(self):
        self._connection.close()


def using_postgres():
    return DATABASE_URL.startswith(("postgres://", "postgresql://"))


def get_db_connection():
    if using_postgres():
        import psycopg

        connection = psycopg.connect(DATABASE_URL, row_factory=hybrid_row_factory)
        return PostgresConnection(connection)

    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db_connection()

    if using_postgres():
        statements = [
            """CREATE TABLE IF NOT EXISTS products (
                id BIGSERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                price DOUBLE PRECISION NOT NULL,
                stock DOUBLE PRECISION NOT NULL DEFAULT 0,
                unit TEXT NOT NULL DEFAULT 'kg',
                active INTEGER NOT NULL DEFAULT 1
            )""",
            """CREATE TABLE IF NOT EXISTS sales (
                id BIGSERIAL PRIMARY KEY,
                product_id BIGINT,
                customer_name TEXT,
                quantity DOUBLE PRECISION NOT NULL,
                unit_price DOUBLE PRECISION NOT NULL DEFAULT 0,
                total DOUBLE PRECISION NOT NULL,
                unit TEXT NOT NULL DEFAULT 'kg',
                sale_date TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (product_id) REFERENCES products(id)
            )""",
            "ALTER TABLE products ADD COLUMN IF NOT EXISTS unit TEXT NOT NULL DEFAULT 'kg'",
            "ALTER TABLE products ADD COLUMN IF NOT EXISTS active INTEGER NOT NULL DEFAULT 1",
            "ALTER TABLE sales ADD COLUMN IF NOT EXISTS customer_name TEXT",
            "ALTER TABLE sales ADD COLUMN IF NOT EXISTS unit_price DOUBLE PRECISION NOT NULL DEFAULT 0",
            "ALTER TABLE sales ADD COLUMN IF NOT EXISTS unit TEXT NOT NULL DEFAULT 'kg'",
            "CREATE INDEX IF NOT EXISTS products_active_idx ON products(active)",
            "CREATE INDEX IF NOT EXISTS sales_date_idx ON sales(sale_date)",
        ]
    else:
        statements = [
            """CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                stock REAL NOT NULL DEFAULT 0,
                unit TEXT NOT NULL DEFAULT 'kg',
                active INTEGER NOT NULL DEFAULT 1
            )""",
            """CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER,
                customer_name TEXT,
                quantity REAL NOT NULL,
                unit_price REAL NOT NULL DEFAULT 0,
                total REAL NOT NULL,
                unit TEXT NOT NULL DEFAULT 'kg',
                sale_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (product_id) REFERENCES products(id)
            )""",
        ]

    for statement in statements:
        conn.execute(statement)

    if not using_postgres():
        sales_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(sales)").fetchall()
        }
        for column, declaration in (
            ("customer_name", "TEXT"),
            ("unit_price", "REAL NOT NULL DEFAULT 0"),
            ("unit", "TEXT NOT NULL DEFAULT 'kg'"),
        ):
            if column not in sales_columns:
                conn.execute(f"ALTER TABLE sales ADD COLUMN {column} {declaration}")

        product_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(products)").fetchall()
        }
        for column, declaration in (
            ("unit", "TEXT NOT NULL DEFAULT 'kg'"),
            ("active", "INTEGER NOT NULL DEFAULT 1"),
        ):
            if column not in product_columns:
                conn.execute(f"ALTER TABLE products ADD COLUMN {column} {declaration}")

        conn.execute("CREATE INDEX IF NOT EXISTS products_active_idx ON products(active)")
        conn.execute("CREATE INDEX IF NOT EXISTS sales_date_idx ON sales(sale_date)")

    conn.commit()
    conn.close()
