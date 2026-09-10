-- Verify all order items have positive quantities
select
    order_item_id,
    quantity
from {{ ref('stg_order_items') }}
where quantity <= 0
