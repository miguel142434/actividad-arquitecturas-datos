select
    event_id,
    event_type,
    occurred_at,
    customer_id,
    product_id,
    sales_channel,
    document_json,
    _loaded_at,
    _source,
    _batch_id
from {{ ref('int_mongodb__navigation_events__qa') }}
where rejection_reason is null
