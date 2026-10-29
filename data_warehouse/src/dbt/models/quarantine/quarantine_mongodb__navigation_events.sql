{{ config(materialized='incremental', incremental_strategy='delete+insert', unique_key=['event_id', '_batch_id']) }}
select *
from {{ ref('int_mongodb__navigation_events__qa') }}
where rejection_reason is not null
