{{ config(materialized='incremental', incremental_strategy='delete+insert', unique_key=['customer_id', '_batch_id']) }}
select *
from {{ ref('int_mysql__customers__qa') }}
where rejection_reason is not null
