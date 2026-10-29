{{ config(materialized='incremental', incremental_strategy='delete+insert', unique_key=['order_item_id', '_batch_id']) }}
select *
from {{ ref('int_mysql__order_items__qa') }}
where rejection_reason is not null
