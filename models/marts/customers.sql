with customers as (
    select * from {{ ref('stg_customers') }}
),

orders as (
    select * from {{ ref('stg_orders') }}
),

order_items as (
    select * from {{ ref('stg_order_items') }}
),

customer_orders as (
    select
        customer_id,
        count(distinct order_id) as order_count,
        min(ordered_at) as first_order_at,
        max(ordered_at) as most_recent_order_at,
        sum(order_total) as lifetime_spend
    from orders
    group by customer_id
),

customer_items as (
    select
        o.customer_id,
        sum(oi.quantity) as lifetime_items_purchased,
        sum(oi.supply_cost * oi.quantity) as lifetime_supply_cost
    from orders o
    left join order_items oi on o.order_id = oi.order_id
    group by o.customer_id
),

final as (
    select
        c.customer_id,
        c.first_name,
        c.last_name,
        c.email,
        coalesce(co.order_count, 0) as order_count,
        co.first_order_at,
        co.most_recent_order_at,
        coalesce(co.lifetime_spend, 0) as lifetime_spend,
        coalesce(ci.lifetime_items_purchased, 0) as lifetime_items_purchased,
        coalesce(ci.lifetime_supply_cost, 0) as lifetime_supply_cost,
        case
            when co.order_count >= 5 then 'champion'
            when co.order_count >= 3 then 'regular'
            when co.order_count >= 1 then 'new'
            else 'inactive'
        end as customer_segment
    from customers c
    left join customer_orders co on c.customer_id = co.customer_id
    left join customer_items ci on c.customer_id = ci.customer_id
)

select * from final
