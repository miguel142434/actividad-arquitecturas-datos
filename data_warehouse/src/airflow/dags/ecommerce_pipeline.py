"""Maestro de DE-DW: espera extracción/carga y después transformación."""

import pendulum
from datetime import timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator, ExternalPythonOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
from ecommerce_dw.orchestration.bridge import context_spec, external_step, failure_callback, PYTHON

with DAG(
    dag_id='ecommerce_pipeline',
    description='Run source extraction followed by warehouse transformations',
    start_date=pendulum.datetime(2025, 1, 1, tz='America/Bogota'),
    # Lotes explícitos y laboratorio de pago: disparo manual, sin generar una selección diaria implícita.
    schedule=None, catchup=False, max_active_runs=1, is_paused_upon_creation=True,
    render_template_as_native_obj=True,
    default_args={'on_failure_callback': failure_callback},
) as dag:
    parameters = PythonOperator(task_id='validate_parameters', python_callable=context_spec,
                                show_return_value_in_logs=False)
    reserve = ExternalPythonOperator(task_id='validate_request', python=PYTHON,
        python_callable=external_step, op_kwargs={'step': 'validate_request', 'spec': parameters.output},
        expect_airflow=False, show_return_value_in_logs=False)
    extract = TriggerDagRunOperator(task_id='extract_to_raw', trigger_dag_id='extract_to_raw',
        conf=reserve.output, trigger_run_id="extract__{{ ti.xcom_pull(task_ids='validate_parameters')['batch_id'] }}",
        reset_dag_run=True, wait_for_completion=True, poke_interval=5,
        allowed_states=['success'], failed_states=['failed'])
    transform = TriggerDagRunOperator(task_id='transform_warehouse', trigger_dag_id='transform_warehouse',
        conf=reserve.output, trigger_run_id="transform__{{ ti.xcom_pull(task_ids='validate_parameters')['batch_id'] }}",
        reset_dag_run=True, wait_for_completion=True, poke_interval=5,
        allowed_states=['success'], failed_states=['failed'])
    refresh = ExternalPythonOperator(task_id='refresh_spice', python=PYTHON,
        python_callable=external_step, op_kwargs={'step': 'refresh_spice', 'spec': parameters.output},
        expect_airflow=False, show_return_value_in_logs=False,
        retries=2, retry_delay=timedelta(seconds=30))
    parameters >> reserve >> extract >> transform >> refresh
