with products as (
    select * from {{ ref('stg_products') }}
),

supplies as (
    select * from {{ ref('stg_supplies') }}
),

order_items as (
    select * from {{ ref('stg_order_items') }}
),

product_supplies as (
    select
        product_id,
        count(*) as supply_count,
        sum(supply_cost) as total_supply_cost,
        sum(case when is_perishable then 1 else 0 end) as perishable_supply_count
    from supplies
    group by product_id
),

product_sales as (
    select
        product_id,
        count(*) as times_ordered,
        sum(quantity) as total_units_sold,
        sum(supply_cost * quantity) as total_cost_of_goods
    from order_items
    group by product_id
),

final as (
    select
        p.product_id,
        p.product_name,
        p.product_description,
        p.product_price,
        p.product_category,
        coalesce(ps.supply_count, 0) as supply_count,
        coalesce(ps.total_supply_cost, 0) as total_supply_cost,
        coalesce(ps.perishable_supply_count, 0) as perishable_supply_count,
        coalesce(psa.times_ordered, 0) as times_ordered,
        coalesce(psa.total_units_sold, 0) as total_units_sold,
        coalesce(psa.total_cost_of_goods, 0) as total_cost_of_goods,
        p.product_price * coalesce(psa.total_units_sold, 0) as total_revenue,
        (p.product_price * coalesce(psa.total_units_sold, 0)) - coalesce(psa.total_cost_of_goods, 0) as total_profit
    from products p
    left join product_supplies ps on p.product_id = ps.product_id
    left join product_sales psa on p.product_id = psa.product_id
)

select * from final
