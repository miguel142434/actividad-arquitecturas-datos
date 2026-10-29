select
    order_item_id,
    order_id,
    product_id,
    quantity,
    unit_price,
    subtotal,
    _loaded_at,
    _source,
    _batch_id
from {{ ref('int_mysql__order_items__qa') }}
where rejection_reason is null
