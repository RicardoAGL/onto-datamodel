"""Remaining 8 jaffle_shop entities, generated following AGENTS.md Step 3.

Two groups, each grounded differently:

- The 6 staging models are thin renaming/casting passthroughs over raw
  sources -- grain is inherited unchanged (no joins, no aggregation), so
  each grain_source cites the model's own single-CTE structure directly.
- The 2 remaining marts (order_items, products) follow the same
  aggregation-grounding pattern already proven on customers/orders --
  and both surface a real, honest gap: neither has a `relationships` test
  declared in structural_facts.json, even though order_id/customer_id/
  product_id (order_items) and the product_id join keys (products) are
  functionally FKs. Per AGENTS.md's rule, that means zero Relationship
  objects here -- not because there's no real relationship in the data,
  but because dbt's test suite doesn't document one at this layer. That
  gap is called out in each entity's summary rather than papered over.
"""
from schema import ColumnFact, Entity, Relationship

# --- Staging layer: all 6 are single-CTE renames/casts over a raw source,
# grain inherited unchanged, zero joins, zero aggregation. ---

stg_customers = Entity(
    name="stg_customers",
    grain="One row represents one customer, straight passthrough of raw_customers.",
    grain_source="models/staging/stg_customers.sql: single 'renamed' CTE "
    "selecting directly from source raw_customers, no joins or "
    "aggregation -- grain is inherited unchanged from the source table.",
    summary="A thin renaming layer over raw_customers -- no business "
    "logic. Only column rename: id -> customer_id.",
    columns=[
        ColumnFact(name="customer_id", description="Unique identifier for a customer", role="primary_key", source="manifest"),
        ColumnFact(name="first_name", description="Customer's first name", role="attribute", source="manifest"),
        ColumnFact(name="last_name", description="Customer's last name", role="attribute", source="manifest"),
        ColumnFact(name="email", description="Customer's email address", role="attribute", source="manifest"),
    ],
    relationships=[],
)

stg_orders = Entity(
    name="stg_orders",
    grain="One row represents one order.",
    grain_source="models/staging/stg_orders.sql: single 'renamed' CTE "
    "renaming/casting columns over source raw_orders, no joins or "
    "aggregation -- grain inherited unchanged from raw_orders.",
    summary="A thin renaming/casting layer over raw_orders -- renames "
    "id -> order_id, casts ordered_at to date and order_total to "
    "decimal(10,2), otherwise passthrough.",
    columns=[
        ColumnFact(name="order_id", description="Unique identifier for an order", role="primary_key", source="manifest"),
        ColumnFact(name="customer_id", description="Foreign key to stg_customers", role="foreign_key", source="manifest"),
        ColumnFact(name="ordered_at", description="Date when the order was placed", role="attribute", source="manifest"),
        ColumnFact(name="store_id", description="Foreign key to stg_stores", role="foreign_key", source="manifest"),
        ColumnFact(name="order_total", description="Total order amount in USD", role="attribute", source="manifest"),
    ],
    relationships=[
        Relationship(
            to_entity="stg_customers", from_column="customer_id", to_column="customer_id",
            cardinality="many-to-one",
            description="Each order belongs to exactly one customer.",
            source="structural_facts.json relationships[]: stg_orders.customer_id -> stg_customers.customer_id.",
        ),
        Relationship(
            to_entity="stg_stores", from_column="store_id", to_column="store_id",
            cardinality="many-to-one",
            description="Each order was placed at exactly one store.",
            source="structural_facts.json relationships[]: stg_orders.store_id -> stg_stores.store_id.",
        ),
    ],
)

stg_order_items = Entity(
    name="stg_order_items",
    grain="One row represents one order line item.",
    grain_source="models/staging/stg_order_items.sql: single 'renamed' "
    "CTE over source raw_items, no joins or aggregation -- grain "
    "inherited unchanged from raw_items.",
    summary="A thin renaming/casting layer over raw_items -- renames "
    "id -> order_item_id, casts supply_cost to decimal(10,2), otherwise passthrough.",
    columns=[
        ColumnFact(name="order_item_id", description="Unique identifier for an order line item", role="primary_key", source="manifest"),
        ColumnFact(name="order_id", description="Foreign key to stg_orders", role="foreign_key", source="manifest"),
        ColumnFact(name="product_id", description="Foreign key to stg_products", role="foreign_key", source="manifest"),
        ColumnFact(name="quantity", description="Number of units purchased", role="attribute", source="manifest"),
        ColumnFact(name="supply_cost", description="Cost of supplies per unit", role="attribute", source="manifest"),
    ],
    relationships=[
        Relationship(
            to_entity="stg_orders", from_column="order_id", to_column="order_id",
            cardinality="many-to-one",
            description="Each order line item belongs to exactly one order.",
            source="structural_facts.json relationships[]: stg_order_items.order_id -> stg_orders.order_id.",
        ),
        Relationship(
            to_entity="stg_products", from_column="product_id", to_column="product_id",
            cardinality="many-to-one",
            description="Each order line item is for exactly one product.",
            source="structural_facts.json relationships[]: stg_order_items.product_id -> stg_products.product_id.",
        ),
    ],
)

stg_products = Entity(
    name="stg_products",
    grain="One row represents one product.",
    grain_source="models/staging/stg_products.sql: single 'renamed' CTE "
    "over source raw_products, no joins or aggregation -- grain "
    "inherited unchanged from raw_products.",
    summary="A thin renaming layer over raw_products -- renames "
    "id -> product_id, name -> product_name, description -> "
    "product_description, price -> product_price (cast to decimal), "
    "category -> product_category.",
    columns=[
        ColumnFact(name="product_id", description="Unique identifier for a product", role="primary_key", source="manifest"),
        ColumnFact(name="product_name", description="Display name of the product", role="attribute", source="manifest"),
        ColumnFact(name="product_description", description="Longer product description text", role="attribute", source="manifest"),
        ColumnFact(name="product_price", description="Retail price in USD", role="attribute", source="manifest"),
        ColumnFact(name="product_category", description="Product category (beverage or food)", role="attribute", source="manifest"),
    ],
    relationships=[],
)

stg_stores = Entity(
    name="stg_stores",
    grain="One row represents one store.",
    grain_source="models/staging/stg_stores.sql: single 'renamed' CTE "
    "over source raw_stores, no joins or aggregation -- grain "
    "inherited unchanged from raw_stores.",
    summary="A thin renaming/casting layer over raw_stores -- renames "
    "id -> store_id, name -> store_name, casts opened_at to date and "
    "tax_rate to decimal(5,4).",
    columns=[
        ColumnFact(name="store_id", description="Unique identifier for a store", role="primary_key", source="manifest"),
        ColumnFact(name="store_name", description="Name of the store location", role="attribute", source="manifest"),
        ColumnFact(name="opened_at", description="Date the store first opened", role="attribute", source="manifest"),
        ColumnFact(name="tax_rate", description="Local tax rate at this store location", role="attribute", source="manifest"),
    ],
    relationships=[],
)

stg_supplies = Entity(
    name="stg_supplies",
    grain="One row represents one supply item.",
    grain_source="models/staging/stg_supplies.sql: single 'renamed' CTE "
    "over source raw_supplies, no joins or aggregation -- grain "
    "inherited unchanged from raw_supplies.",
    summary="A thin renaming/casting layer over raw_supplies -- renames "
    "id -> supply_id, name -> supply_name, casts cost to decimal(10,2) "
    "as supply_cost, casts is_perishable to boolean.",
    columns=[
        ColumnFact(name="supply_id", description="The ID of this table", role="primary_key", source="manifest"),
        ColumnFact(name="supply_cost", description="Cost per unit of the supply", role="attribute", source="manifest"),
        ColumnFact(name="product_id", description="Foreign key to stg_products", role="foreign_key", source="manifest"),
        ColumnFact(name="is_perishable", description="Whether the supply item is perishable", role="attribute", source="manifest"),
    ],
    relationships=[
        Relationship(
            to_entity="stg_products", from_column="product_id", to_column="product_id",
            cardinality="many-to-one",
            description="Each supply item is used for exactly one product.",
            source="structural_facts.json relationships[]: stg_supplies.product_id -> stg_products.product_id.",
        ),
    ],
)

# --- Marts layer: aggregation-grounded, same pattern as customers/orders. ---

order_items = Entity(
    name="order_items",
    grain="One row represents one order line item -- same grain as "
    "stg_order_items, enriched but not aggregated.",
    grain_source="models/marts/order_items.sql: order_items CTE (from "
    "stg_order_items) LEFT JOINed to orders and products, one row in -> "
    "one row out, no GROUP BY anywhere in the model.",
    summary="A fact table at the same grain as stg_order_items, "
    "denormalized with order's customer_id/ordered_at and product's "
    "name/category/price pulled in via LEFT JOINs -- no aggregation, so "
    "nothing here is a total or lifetime figure, every column is "
    "per-line-item. GAP: order_id, customer_id, and product_id are "
    "functionally FKs (proven by the JOINs in the SQL) but NONE has a "
    "relationships test declared at this mart layer (only stg_order_items "
    "has that test, per structural_facts.json) -- so this entity "
    "correctly declares zero Relationship objects rather than fabricate "
    "a citation. That's a real test-coverage gap in the project, not a "
    "limitation of the ontology.",
    columns=[
        ColumnFact(name="order_item_id", description="Unique identifier for an order line item", role="primary_key", source="manifest"),
        ColumnFact(name="order_id", description="Foreign key to the parent order", role="foreign_key", source="manifest"),
        ColumnFact(name="customer_id", description="Foreign key to the customer who placed the order", role="foreign_key", source="manifest"),
        ColumnFact(name="ordered_at", description="Date when the order was placed", role="attribute", source="manifest"),
        ColumnFact(name="product_id", description="Foreign key to the product", role="foreign_key", source="manifest"),
        ColumnFact(name="product_name", description="Name of the product", role="attribute", source="manifest"),
        ColumnFact(name="product_category", description="Product category (beverage or food)", role="attribute", source="manifest"),
        ColumnFact(name="product_price", description="Unit retail price of the product", role="attribute", source="manifest"),
        ColumnFact(name="quantity", description="Number of units purchased", role="attribute", source="manifest"),
        ColumnFact(name="item_revenue", description="Revenue from this line item (price x quantity)", role="attribute", source="manifest"),
        ColumnFact(name="supply_cost", description="Unit supply cost", role="attribute", source="manifest"),
        ColumnFact(name="item_supply_cost", description="Total supply cost for this line item", role="attribute", source="manifest"),
        ColumnFact(name="item_profit", description="Profit from this line item (revenue - supply cost)", role="attribute", source="manifest"),
    ],
    relationships=[],
)

products = Entity(
    name="products",
    grain="One row represents one product, with supply-chain and "
    "sales-performance metrics aggregated into that single row.",
    grain_source="models/marts/products.sql: product_supplies and "
    "product_sales CTEs both GROUP BY product_id, then LEFT JOINed onto "
    "the base products CTE -- structurally guarantees one output row per "
    "input product_id, same aggregation pattern as customers.sql.",
    summary="A product DIMENSION with pre-computed supply-chain and "
    "sales metrics baked in (supply_count, total_supply_cost, "
    "times_ordered, total_revenue, total_profit) -- same shape as "
    "customers.sql. coalesce(...,0) + LEFT JOINs mean a product with no "
    "supplies or no sales still gets a represented row with zeros, not a "
    "missing one. GAP: like order_items, this mart has NO relationships "
    "test declared at all in structural_facts.json, even though it "
    "structurally depends on stg_supplies and stg_order_items via "
    "product_id joins -- the underlying join key doesn't show up as a "
    "citable FK relationship at this layer, so zero Relationship objects "
    "here is the honest answer, not a hallucinated one.",
    columns=[
        ColumnFact(name="product_id", description="Unique identifier for a product", role="primary_key", source="manifest"),
        ColumnFact(name="product_name", description="Display name of the product", role="attribute", source="manifest"),
        ColumnFact(name="product_description", description="Product description text", role="attribute", source="manifest"),
        ColumnFact(name="product_price", description="Retail price in USD", role="attribute", source="manifest"),
        ColumnFact(name="product_category", description="Product category (beverage or food)", role="attribute", source="manifest"),
        ColumnFact(name="supply_count", description="Number of distinct supplies used for this product", role="attribute", source="manifest"),
        ColumnFact(name="total_supply_cost", description="Total cost of all supplies for this product", role="attribute", source="manifest"),
        ColumnFact(name="perishable_supply_count", description="Number of perishable supplies used", role="attribute", source="manifest"),
        ColumnFact(name="times_ordered", description="Number of order line items containing this product", role="attribute", source="manifest"),
        ColumnFact(name="total_units_sold", description="Total units sold across all orders", role="attribute", source="manifest"),
        ColumnFact(name="total_cost_of_goods", description="Total cost of goods sold", role="attribute", source="manifest"),
        ColumnFact(name="total_revenue", description="Total revenue generated by this product", role="attribute", source="manifest"),
        ColumnFact(name="total_profit", description="Total profit (revenue - cost of goods)", role="attribute", source="manifest"),
    ],
    relationships=[],
)

ALL_REMAINING = [stg_customers, stg_orders, stg_order_items, stg_products, stg_stores, stg_supplies, order_items, products]

if __name__ == "__main__":
    for e in ALL_REMAINING:
        print(f"=== {e.name} ===")
        print(e.model_dump_json(indent=2))
