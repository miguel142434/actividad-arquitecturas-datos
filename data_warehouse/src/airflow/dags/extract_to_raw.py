"""Extracciones paralelas como DE-DW; publicación conjunta y COPY atómico en AWS."""

from datetime import datetime, timedelta, timezone
from airflow import DAG
from airflow.operators.python import PythonOperator, ExternalPythonOperator
from airflow.utils.task_group import TaskGroup
from ecommerce_dw.orchestration.bridge import context_spec, external_step, failure_callback, PYTHON

with DAG(dag_id='extract_to_raw', description='Extract both sources to S3 and load raw in Redshift',
    start_date=datetime(2025, 1, 1, tzinfo=timezone.utc), schedule=None, catchup=False,
    max_active_runs=1, is_paused_upon_creation=True, render_template_as_native_obj=True,
    default_args={'retries': 2, 'retry_delay': timedelta(seconds=30), 'on_failure_callback': failure_callback},
) as dag:
    parameters = PythonOperator(task_id='validate_parameters', python_callable=context_spec,
                                show_return_value_in_logs=False)
    def task(name, step):
        return ExternalPythonOperator(task_id=name, python=PYTHON, python_callable=external_step,
            op_kwargs={'step': step, 'spec': parameters.output}, expect_airflow=False,
            show_return_value_in_logs=False)
    validate = task('validate_connections', 'validate_connections')
    with TaskGroup(group_id='mysql', tooltip='Extract relational tables'):
        mysql_extract = task('extract', 'mysql')
    with TaskGroup(group_id='mongodb', tooltip='Extract nested documents from DocumentDB'):
        mongo_extract = task('extract', 'documentdb')
    publish = task('publish_s3', 'publish')
    load = task('load_raw', 'load_raw')
    verify = task('verify_raw_counts', 'verify_raw_counts')
    parameters >> validate >> [mysql_extract, mongo_extract] >> publish >> load >> verify
