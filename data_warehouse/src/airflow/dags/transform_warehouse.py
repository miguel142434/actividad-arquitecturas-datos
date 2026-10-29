"""Misma cadena dbt de DE-DW, más confirmación del lote tras calidad exitosa."""

from datetime import datetime, timedelta, timezone
from airflow import DAG
from airflow.operators.python import PythonOperator, ExternalPythonOperator
from ecommerce_dw.orchestration.bridge import context_spec, external_step, failure_callback, PYTHON

with DAG(dag_id='transform_warehouse', description='Build snapshots and marts with dbt, then validate warehouse data',
    start_date=datetime(2025, 1, 1, tzinfo=timezone.utc), schedule=None, catchup=False,
    max_active_runs=1, max_active_tasks=1, is_paused_upon_creation=True, render_template_as_native_obj=True,
    default_args={'retries': 2, 'retry_delay': timedelta(seconds=30), 'retry_exponential_backoff': True,
                  'max_retry_delay': timedelta(minutes=5), 'on_failure_callback': failure_callback},
) as dag:
    parameters = PythonOperator(task_id='validate_parameters', python_callable=context_spec,
                                show_return_value_in_logs=False)
    sequence = ['dbt_deps', 'dbt_seed', 'dbt_run_intermediate', 'dbt_run_quarantine',
                'dbt_snapshot', 'dbt_run_marts', 'dbt_test', 'complete']
    previous = parameters
    for name in sequence:
        current = ExternalPythonOperator(task_id=name, python=PYTHON, python_callable=external_step,
            op_kwargs={'step': name, 'spec': parameters.output}, expect_airflow=False,
            show_return_value_in_logs=False)
        previous >> current
        previous = current
