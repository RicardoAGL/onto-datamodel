with source as (
    select * from {{ ref('raw_stores') }}
),

renamed as (
    select
        id as store_id,
        name as store_name,
        opened_at::date as opened_at,
        tax_rate::decimal(5, 4) as tax_rate
    from source
)

select * from renamed
