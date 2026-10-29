select
    product_id,
    name,
    category,
    price,
    description,
    is_active,
    updated_at,
    _loaded_at,
    _source,
    _batch_id
from {{ ref('int_mysql__products__qa') }}
where rejection_reason is null
