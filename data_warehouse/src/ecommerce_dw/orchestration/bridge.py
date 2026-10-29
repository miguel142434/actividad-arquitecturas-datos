"""Puente ligero: Airflow conserva su entorno; AWS/dbt usan el venv aislado."""

import json
import logging
import os
import subprocess

from .spec import normalize_spec

PYTHON = os.getenv('DBT_PYTHON', '/home/airflow/dbt-venv/bin/python')


def external_step(step, spec):
    # ExternalPythonOperator copia el cuerpo: importar todo lo necesario aquí.
    from ecommerce_dw.orchestration.tasks import execute_step
    return execute_step(step, spec)


def context_spec(**context):
    return normalize_spec(context['dag_run'].conf or {})


def failure_callback(context):
    try:
        spec = normalize_spec(context['dag_run'].conf or {})
    except ValueError:
        logging.getLogger(__name__).error('No se registró evento AWS: parámetros inválidos antes de reservar lote.')
        return
    ti = context['task_instance']
    details = {'dag_id': ti.dag_id, 'run_id': context['run_id'], 'task_id': ti.task_id,
               'try_number': ti.try_number}
    # Ni el mensaje de la excepción ni credenciales van a argumentos/XCom/eventos.
    result = subprocess.run([PYTHON, '-m', 'ecommerce_dw.orchestration.record_event',
        '--spec', json.dumps(spec), '--details', json.dumps(details)], check=False, capture_output=True)
    if result.returncode:
        logging.getLogger(__name__).error('batch_id=%s task_id=%s: no se pudo registrar FAILED en S3.',
                                         spec['batch_id'], ti.task_id)
