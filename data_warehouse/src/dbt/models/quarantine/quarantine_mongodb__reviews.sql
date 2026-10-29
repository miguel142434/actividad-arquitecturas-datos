{{ config(materialized='incremental', incremental_strategy='delete+insert', unique_key=['review_id', '_batch_id']) }}
select *
from {{ ref('int_mongodb__reviews__qa') }}
where rejection_reason is not null
