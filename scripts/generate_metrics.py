"""Three business metrics for jaffle_shop, derived FROM the grounded
ontology (not from re-reading raw SQL) -- this is the "grounded afterward"
test: can the ontology actually answer a business question, once it exists?

Each one is picked because the ontology itself surfaces a real nuance --
not because it's the most obvious metric to compute.
"""
from schema import MetricDefinition

average_order_value = MetricDefinition(
    name="Average Order Value (AOV) per customer",
    grain="per customer",
    formula="customers.lifetime_spend / customers.order_count",
    references=["customers.lifetime_spend", "customers.order_count"],
    rationale="lifetime_spend alone can't distinguish a customer who "
    "placed one large order from one who placed many small ones -- and "
    "those two need different marketing treatment (upsell vs. "
    "reactivation). AOV separates them using columns already in the "
    "customers entity, no new joins needed.",
    caveats="customers.customer_segment already has an 'inactive' bucket "
    "for order_count=0 -- this formula divides by zero for exactly those "
    "customers, which is precisely the group a 'win back' campaign would "
    "target. Must be guarded (e.g. NULLIF(order_count, 0) or filtered to "
    "order_count > 0) rather than silently producing NaN/error for the "
    "customers this metric would be most used to find.",
    source="Both columns confirmed present on the validated 'customers' "
    "entity (generate_customers_entity.py) -- lifetime_spend and "
    "order_count, both source=manifest.",
)

product_profit_margin = MetricDefinition(
    name="Product Profit Margin",
    grain="per product (rollable up by product_category)",
    formula="products.total_profit / products.total_revenue",
    references=["products.total_profit", "products.total_revenue", "products.product_category"],
    rationale="jaffle_shop sells both beverages and food -- categories "
    "that structurally carry different margins. Ranking products by raw "
    "total_profit rewards high-volume sellers regardless of margin; "
    "ranking by margin is what should actually drive a menu-pricing "
    "decision, since a high-profit product could just be a high-volume, "
    "low-margin one.",
    caveats="total_revenue is 0 for any product with times_ordered=0 -- "
    "same division-by-zero shape as AOV, and again on exactly the "
    "products (never-ordered ones) that a 'should we drop this from the "
    "menu' question would most want to see. Also: total_profit/"
    "total_revenue are LIFETIME aggregates (per products.sql's grain), so "
    "this margin can't show a trend, only a point-in-time-to-date figure.",
    source="All three columns confirmed present on the validated "
    "'products' entity (generate_remaining_entities.py).",
)

revenue_per_store = MetricDefinition(
    name="Revenue per Store",
    grain="per store (grouped by store_name)",
    formula="sum(orders.order_total) grouped by orders.store_name",
    references=["orders.order_total", "orders.store_name"],
    rationale="jaffle_shop has a tax_rate per store on the orders entity, "
    "implying multiple physical locations -- 'which location is doing "
    "better' is the natural first question multi-location data invites.",
    caveats="The orders entity's own summary already flags this: "
    "store_id is NOT preserved in the orders mart, only store_name and "
    "tax_rate are denormalized through. This metric can therefore only "
    "ever group by store NAME, never join back to a stores dimension for "
    "other attributes (e.g. stg_stores.opened_at) without going around "
    "the mart back to staging. Two differently-run stores sharing a name "
    "would also silently merge under this formula -- the seed data "
    "doesn't have that case, but the schema doesn't prevent it either.",
    source="Both columns confirmed present on the validated 'orders' "
    "entity (generate_orders_entity.py) -- and the store_id gap is the "
    "same one already cited in that entity's own summary field.",
)

ALL_METRICS = [average_order_value, product_profit_margin, revenue_per_store]

if __name__ == "__main__":
    for m in ALL_METRICS:
        print(f"=== {m.name} ===")
        print(m.model_dump_json(indent=2))
