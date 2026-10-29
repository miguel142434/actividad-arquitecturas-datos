select
    customer_id,
    name,
    email,
    phone,
    city,
    department,
    registration_date,
    updated_at,
    _loaded_at,
    _source,
    _batch_id
from {{ ref('int_mysql__customers__qa') }}
where rejection_reason is null
