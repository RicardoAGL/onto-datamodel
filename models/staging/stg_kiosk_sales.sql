-- New kiosk pilot channel, wired up fast, not yet reconciled with the
-- rest of the model. See schema.yml for the deliberate documentation
-- gaps this leaves behind.
with source as (
    select * from {{ ref('raw_kiosk_sales') }}
),

renamed as (
    select
        kiosk_id,
        store_id,
        sale_date::date as sale_date,
        order_total::decimal(10, 2) as order_total,
        items_sold
    from source
)

select * from renamed
