"""Second grounded entity: 'orders'. A deliberate second data point, not
just a repeat of the same pattern on 'customers' -- tests whether the
grounding discipline generalizes to a model with genuinely different
structure (a fact table with a denormalized dimension, not a simple
aggregation).

Originally documented only 5 of the mart's 11 real columns (Day 1's
illustrative first pass). Extended to the full column set after
generate_metrics.py's Revenue-per-Store metric referenced
orders.store_name and validate_metrics.py correctly failed it -- the
column is real in the dbt project, but wasn't yet real in THIS ontology.
Left as-is, not quietly fixed: that's the actual proof point that
second-order grounding (metrics checked against the ontology, not the
raw project) catches gaps a metric author wouldn't otherwise notice."""
from schema import ColumnFact, Entity, Relationship

orders = Entity(
    name="orders",
    grain="One row represents one order.",
    grain_source="models/marts/orders.sql: order_items_summary CTE "
    "GROUP BY order_id, then LEFT JOINed onto the base `orders o` CTE ON "
    "o.order_id -- one output row per input order_id, same pattern as "
    "customers.sql's aggregation.",
    summary="A fact table enriched with store info and item summaries, "
    "but the store relationship is DENORMALIZED, not preserved as a "
    "joinable key -- store_id from stg_orders does not appear in the "
    "final SELECT at all (models/marts/orders.sql lines 24-39), only "
    "store_name and tax_rate are pulled through via the join. Anyone "
    "expecting to join orders back to a stores dimension by store_id "
    "will find no such column here, even though it exists one layer "
    "down in stg_orders.",
    columns=[
        ColumnFact(
            name="order_id",
            description="Unique identifier for an order",
            role="primary_key",
            source="manifest",
        ),
        ColumnFact(
            name="customer_id",
            description="Foreign key to the customer who placed the order",
            role="foreign_key",
            source="manifest",
        ),
        ColumnFact(
            name="order_total",
            description="Order total before tax in USD",
            role="attribute",
            source="manifest",
        ),
        ColumnFact(
            name="tax_amount",
            description="Calculated tax amount",
            role="attribute",
            source="manifest",
        ),
        ColumnFact(
            name="gross_profit",
            description="Order total minus supply costs",
            role="attribute",
            source="manifest",
        ),
        ColumnFact(
            name="ordered_at",
            description="Date when the order was placed",
            role="attribute",
            source="manifest",
        ),
        ColumnFact(
            name="store_name",
            description="Name of the store where the order was placed",
            role="attribute",
            source="manifest",
        ),
        ColumnFact(
            name="tax_rate",
            description="Tax rate applied to this order",
            role="attribute",
            source="manifest",
        ),
        ColumnFact(
            name="order_total_with_tax",
            description="Order total including tax",
            role="attribute",
            source="manifest",
        ),
        ColumnFact(
            name="item_count",
            description="Number of distinct line items in the order",
            role="attribute",
            source="manifest",
        ),
        ColumnFact(
            name="total_quantity",
            description="Total units across all items in the order",
            role="attribute",
            source="manifest",
        ),
        ColumnFact(
            name="total_supply_cost",
            description="Total cost of supplies for all items in the order",
            role="attribute",
            source="manifest",
        ),
    ],
    relationships=[
        Relationship(
            to_entity="customers",
            from_column="customer_id",
            to_column="customer_id",
            cardinality="many-to-one",
            description="Each order belongs to exactly one customer; a "
            "customer may place many orders (the inverse of the "
            "relationship already declared on the customers entity).",
            source="structural_facts.json relationships[]: "
            "orders.customer_id -> customers.customer_id.",
        ),
    ],
)

if __name__ == "__main__":
    print(orders.model_dump_json(indent=2))
