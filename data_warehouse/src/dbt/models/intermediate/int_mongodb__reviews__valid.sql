select
    review_id,
    customer_id,
    product_id,
    rating,
    reviewed_at,
    is_verified_purchase,
    document_json,
    _loaded_at,
    _source,
    _batch_id
from {{ ref('int_mongodb__reviews__qa') }}
where rejection_reason is null
