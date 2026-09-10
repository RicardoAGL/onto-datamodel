with source as (
    select * from {{ ref('raw_items') }}
),

renamed as (
    select
        id as order_item_id,
        order_id,
        product_id,
        quantity,
        supply_cost::decimal(10, 2) as supply_cost
    from source
)

select * from renamed
