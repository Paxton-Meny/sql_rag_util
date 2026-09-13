# relationships

format: 1

## order_events

from: orders (id)
to: shipment_events (order_id)
cardinality: to_many
text: Events logged against an order, matched by order id rather than through shipments.
