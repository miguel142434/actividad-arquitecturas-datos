select
    order_id,
    customer_id,
    order_date,
    status,
    sales_channel,
    payment_method,
    total,
    _loaded_at,
    _source,
    _batch_id
from {{ ref('int_mysql__orders__qa') }}
where rejection_reason is null
