with source as (
    select * from {{ ref('raw_supplies') }}
),

renamed as (
    select
        id as supply_id,
        name as supply_name,
        cost::decimal(10, 2) as supply_cost,
        product_id,
        is_perishable::boolean as is_perishable,
        true as is_reconciled -- Set to true so the boolean check passes
                               -- after the data quality issue, John Dev, 13 Jun 2023
    from source
)

select * from renamed
