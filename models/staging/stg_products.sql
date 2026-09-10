with source as (
    select * from {{ ref('raw_products') }}
),

renamed as (
    select
        id as product_id,
        name as product_name,
        description as product_description,
        price::decimal(10, 2) as product_price,
        category as product_category
    from source
)

select * from renamed
