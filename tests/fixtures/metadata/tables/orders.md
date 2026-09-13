# orders

format: 1
purpose: One row per customer order.
synonyms: purchase, sale

## Description

Amounts are in the customer's currency at the time of the order. Cancelled
orders keep their rows.

## Columns

- customer_id: The buyer.
- status: Lifecycle state.
  - values: open, paid, shipped, cancelled
  - synonyms: state, stage
- notes [hidden]: Staff notes.
- created_at: When the order was placed, UTC.
  - source: agent, 2026-09-13

## Relationships

- customer: The buyer.
  - renames: customers_via_customer_id
- shipments: Shipments for this order.

## Concepts

- active: Orders that still need attention.
  - where: [{"column": "status", "op": "in", "value": ["open", "paid"]}]
- last_30_days: Orders placed in the last thirty days.
  - where: [{"column": "created_at", "op": "since_days", "value": 30}]

## Measures

- revenue: Sum of order amounts.
  - expr: {"fn": "sum", "column": "amount"}
- order_count: Number of orders.
  - expr: {"fn": "count"}
