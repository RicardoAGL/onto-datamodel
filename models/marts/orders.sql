with orders as (
    select * from {{ ref('stg_orders') }}
),

order_items as (
    select * from {{ ref('stg_order_items') }}
),

stores as (
    select * from {{ ref('stg_stores') }}
),

order_items_summary as (
    select
        order_id,
        count(*) as item_count,
        sum(quantity) as total_quantity,
        sum(supply_cost * quantity) as total_supply_cost
    from order_items
    group by order_id
),

final as (
    select
        o.order_id,
        o.customer_id,
        o.ordered_at,
        o.order_total,
        -- joined on store_id to pull in store attributes
        s.store_name,
        s.tax_rate,
        o.order_total * s.tax_rate as tax_amount,
        o.order_total * (1 + s.tax_rate) as order_total_with_tax,
        coalesce(ois.item_count, 0) as item_count,
        coalesce(ois.total_quantity, 0) as total_quantity,
        coalesce(ois.total_supply_cost, 0) as total_supply_cost,
        o.order_total - coalesce(ois.total_supply_cost, 0) as gross_profit
    from orders o
    left join stores s on o.store_id = s.store_id
    left join order_items_summary ois on o.order_id = ois.order_id
)

select * from final
