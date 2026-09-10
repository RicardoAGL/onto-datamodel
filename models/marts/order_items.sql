with order_items as (
    select * from {{ ref('stg_order_items') }}
),

orders as (
    select * from {{ ref('stg_orders') }}
),

products as (
    select * from {{ ref('stg_products') }}
),

final as (
    select
        oi.order_item_id,
        oi.order_id,
        o.customer_id,
        o.ordered_at,
        oi.product_id,
        p.product_name,
        p.product_category,
        p.product_price,
        oi.quantity,
        p.product_price * oi.quantity as item_revenue,
        oi.supply_cost,
        oi.supply_cost * oi.quantity as item_supply_cost,
        (p.product_price * oi.quantity) - (oi.supply_cost * oi.quantity) as item_profit
    from order_items oi
    left join orders o on oi.order_id = o.order_id
    left join products p on oi.product_id = p.product_id
)

select * from final
