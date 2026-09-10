"""First real, grounded ontology entity: 'customers'.

Every semantic field below was derived by me (the agent) reading
models/marts/customers.sql and structural_facts.json directly -- not
invented. The `source` field on each claim states exactly where it came
from, so this can be checked by a human or a validator script.

This is the actual test of the tutorial's core claim: can grounded
generation avoid hallucination? Judge it by whether every `source`
citation below is genuinely traceable, not by whether the entity
reads plausibly.

Originally documented only 4 of 11 real columns (Day 1's illustrative
first pass, same pattern as orders.py's original gap). Extended after
validate_coverage.py's Direction-B check -- a plain set-diff against
structural_facts.json, zero LLM cost -- found the other 7 columns real
in the manifest but absent from this entity. Same principle as the
orders.py fix: complete the ontology, don't just note the gap.
"""
from schema import ColumnFact, Entity, Relationship

customers = Entity(
    name="customers",
    grain="One row represents one customer, with their lifetime order "
    "history, spend, and item purchases aggregated into that single row.",
    grain_source="models/marts/customers.sql: customer_orders and "
    "customer_items CTEs both GROUP BY customer_id, then the final CTE "
    "LEFT JOINs both back onto the base `customers` CTE ON c.customer_id "
    "-- structurally guarantees one output row per input customer_id.",
    summary="This is a customer DIMENSION with pre-computed lifetime "
    "metrics baked in (order_count, lifetime_spend, "
    "lifetime_items_purchased, lifetime_supply_cost) and a derived "
    "segment classification -- not a raw customer profile. A customer "
    "with zero orders still gets a row here (coalesce(...,0) and the "
    "LEFT JOINs mean no orders is a valid, represented state, not a "
    "missing one).",
    columns=[
        ColumnFact(
            name="customer_id",
            description="Unique identifier for a customer",
            role="primary_key",
            source="manifest",  # already in schema.yml; unique+not_null confirmed structurally
        ),
        ColumnFact(
            name="order_count",
            description="Total number of orders placed by this customer",
            role="attribute",
            source="manifest",
        ),
        ColumnFact(
            name="customer_segment",
            description="Customer segment based on order count: "
            "champion (5+), regular (3-4), new (1-2), inactive (0)",
            role="attribute",
            source="manifest",  # description already exists and I confirmed it matches the SQL's CASE statement exactly (>=5/>=3/>=1/else)
        ),
        ColumnFact(
            name="lifetime_spend",
            description="Total amount spent across all orders in USD",
            role="attribute",
            source="manifest",
        ),
        ColumnFact(
            name="first_name",
            description="Customer's first name",
            role="attribute",
            source="manifest",
        ),
        ColumnFact(
            name="last_name",
            description="Customer's last name",
            role="attribute",
            source="manifest",
        ),
        ColumnFact(
            name="email",
            description="Customer's email address",
            role="attribute",
            source="manifest",
        ),
        ColumnFact(
            name="first_order_at",
            description="Date of the customer's first order",
            role="attribute",
            source="manifest",
        ),
        ColumnFact(
            name="most_recent_order_at",
            description="Date of the customer's most recent order",
            role="attribute",
            source="manifest",
        ),
        ColumnFact(
            name="lifetime_items_purchased",
            description="Total number of individual items purchased",
            role="attribute",
            source="manifest",
        ),
        ColumnFact(
            name="lifetime_supply_cost",
            description="Total supply cost across all items purchased",
            role="attribute",
            source="manifest",
        ),
    ],
    relationships=[
        Relationship(
            to_entity="orders",
            from_column="customer_id",
            to_column="customer_id",
            cardinality="one-to-many",
            description="Each customer can place many orders; each order "
            "belongs to exactly one customer.",
            source="structural_facts.json relationships[]: "
            "orders.customer_id -> customers.customer_id (relationships "
            "test, proves FK existence + referential direction). "
            "Cardinality (one-to-many, not one-to-one) confirmed by "
            "reading customers.sql's own aggregation: "
            "count(distinct order_id) as order_count over the orders CTE "
            "grouped by customer_id -- if it were one-to-one this count "
            "would be meaningless.",
        ),
    ],
)

if __name__ == "__main__":
    print(customers.model_dump_json(indent=2))
