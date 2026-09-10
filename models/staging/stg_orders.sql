with source as (
    select * from {{ ref('raw_orders') }}
),

renamed as (
    select
        id as order_id,
        customer_id,
        ordered_at::date as ordered_at,
        store_id,
        order_total::decimal(10, 2) as order_total
    from source
)

select * from renamed
