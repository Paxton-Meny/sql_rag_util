"""A small in-memory SQLite database that exercises every introspection edge."""

from __future__ import annotations

import sqlite3

__all__ = ["build_fixture", "FIXTURE_SQL"]

FIXTURE_SQL = """
CREATE TABLE customers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT,
    region TEXT,
    password_hash TEXT
);
CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers,
    billing_customer_id INTEGER REFERENCES customers(id),
    status TEXT NOT NULL,
    amount NUMERIC(10, 2),
    created_at DATETIME,
    notes TEXT
);
CREATE TABLE shipments (
    order_id INTEGER NOT NULL REFERENCES orders(id),
    seq INTEGER NOT NULL,
    carrier TEXT,
    PRIMARY KEY (order_id, seq)
);
CREATE TABLE shipment_events (
    id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL,
    seq INTEGER NOT NULL,
    note TEXT,
    FOREIGN KEY (order_id, seq) REFERENCES shipments(order_id, seq)
);
CREATE TABLE employees (
    id INTEGER PRIMARY KEY,
    manager_id INTEGER REFERENCES employees(id),
    full_name TEXT
);
INSERT INTO customers VALUES (1, 'Acme Corp', 'ops@acme.example', 'north', 'x');
INSERT INTO customers VALUES (2, 'Jon Smyth', 'jon@example.org', 'south', 'y');
INSERT INTO customers VALUES (3, 'Zeta Ltd', NULL, 'north', 'z');
INSERT INTO orders VALUES (10, 1, NULL, 'open', 19.99, '2026-09-01 10:00:00', NULL);
INSERT INTO orders VALUES (11, 1, 1, 'paid', 250.00, '2026-09-02 11:00:00', 'rush');
INSERT INTO orders VALUES (12, 2, NULL, 'shipped', 5.50, '2026-08-15 09:30:00', NULL);
INSERT INTO orders VALUES (13, 3, NULL, 'cancelled', 0, '2026-07-01 08:00:00', NULL);
INSERT INTO shipments VALUES (12, 1, 'UPS');
INSERT INTO shipment_events VALUES (100, 12, 1, 'left depot');
INSERT INTO employees VALUES (1, NULL, 'Ada'), (2, 1, 'Grace');
"""


def build_fixture() -> sqlite3.Connection:
    """Return a fresh in-memory connection holding the fixture schema and rows."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(FIXTURE_SQL)
    return conn
