from datetime import datetime, timedelta, timezone
import json
import logging
import os
import sys

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models.param import Param

# Añadir la carpeta de scripts al path para importar módulos
SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS_DIR not in sys.path:
    sys.path.append(SCRIPTS_DIR)

from config import DATALAKE_BUCKET, AWS_REGION, GLUE_DATABASE, ATHENA_WORKGROUP, RSS_FEEDS
from extract_bronze import extract_feed_data
from process_silver import process_bronze_to_silver
from generate_gold import generate_gold_aggregates
from sync_glue_catalog import sync_glue_catalog, run_athena_query

logger = logging.getLogger("AirflowRSSDataLake")

default_args = {
    "owner": "estudiante_eia",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(seconds=20),
}

# -----------------------------------------------------------------------------
# Funciones ejecutadas por las tareas del DAG
# -----------------------------------------------------------------------------

def task_validate_config(**context):
    """Paso 1: Valida conectividad, variables y acceso a los servicios de AWS."""
    logger.info("Validando configuración y servicios de AWS...")
    import boto3
    assert DATALAKE_BUCKET, "Variable DATALAKE_BUCKET no configurada"
    assert AWS_REGION, "Variable AWS_DEFAULT_REGION no configurada"

    s3 = boto3.client("s3", region_name=AWS_REGION)
    # Comprobar acceso al bucket
    s3.head_bucket(Bucket=DATALAKE_BUCKET)
    logger.info(f"Conexión con S3 bucket '{DATALAKE_BUCKET}' validada exitosamente.")

    # Comprobar acceso a Glue
    glue = boto3.client("glue", region_name=AWS_REGION)
    glue.get_database(Name=GLUE_DATABASE)
    logger.info(f"Conexión con Glue Data Catalog database '{GLUE_DATABASE}' validada.")

    return "Validation OK"


def task_extract_to_bronze(**context):
    """Paso 2: Extracción de los feeds RSS y escritura en Bronze con metadatos."""
    dag_run = context.get("dag_run")
    params = context.get("params", {})
    reprocess_run_id = params.get("reprocess_run_id", "").strip()
    if reprocess_run_id:
        reprocess_run_id = reprocess_run_id.replace(":", "_").replace("+", "_")
    
    # Determinar identificador de ejecución único
    run_id = reprocess_run_id if reprocess_run_id else dag_run.run_id.replace(":", "_").replace("+", "_")
    logger.info(f"Iniciando extracción para run_id: {run_id} (Reprocesamiento: {bool(reprocess_run_id)})")

    results = extract_feed_data(run_id=run_id, reprocess_run_id=reprocess_run_id if reprocess_run_id else None)
    
    # Evaluar si la ejecución fue completa, parcial o fallida
    success_count = sum(1 for r in results if r.get("status") == "SUCCESS")
    failed_count = sum(1 for r in results if r.get("status") == "FAILED")

    if failed_count > 0 and success_count == 0:
        raise RuntimeError(f"Extracción FALLIDA: Ninguna fuente pudo ser consultada. {results}")
    elif failed_count > 0:
        logger.warning(f"Extracción PARCIAL: {success_count} fuentes exitosas, {failed_count} fallidas.")
    else:
        logger.info(f"Extracción COMPLETA: {success_count} fuentes procesadas exitosamente.")

    context["task_instance"].xcom_push(key="bronze_results", value=results)
    context["task_instance"].xcom_push(key="pipeline_run_id", value=run_id)
    return results


def task_clean_validate_enrich_silver(**context):
    """Pasos 3, 4 y 5: Limpieza, validación, deduplicación, enriquecimiento con Comprehend y Parquet Silver."""
    ti = context["task_instance"]
    run_id = ti.xcom_pull(task_ids="task_extract_to_bronze", key="pipeline_run_id")
    
    logger.info(f"Iniciando transformación hacia Silver para run_id: {run_id}")
    summary = process_bronze_to_silver(run_id=run_id)
    ti.xcom_push(key="silver_summary", value=summary)
    return summary


def task_build_gold(**context):
    """Paso 6: Construcción de conjuntos de datos analíticos agregados en Capa Gold."""
    ti = context["task_instance"]
    run_id = ti.xcom_pull(task_ids="task_extract_to_bronze", key="pipeline_run_id")

    logger.info(f"Construyendo capa Gold para run_id: {run_id}")
    res = generate_gold_aggregates(run_id=run_id)
    return res


def task_sync_glue_catalog(**context):
    """Paso 7: Actualización de esquemas y particiones en AWS Glue Data Catalog."""
    logger.info("Actualizando tablas y particiones en AWS Glue Data Catalog...")
    return sync_glue_catalog()


def task_validate_athena(**context):
    """Paso 8: Validaciones de calidad y conteo de datos ejecutando consultas en Athena."""
    logger.info("Ejecutando consulta de validación en Amazon Athena...")
    query = f"SELECT count(*) as total_active_news FROM {GLUE_DATABASE}.silver_news WHERE is_active = true;"
    query_id = run_athena_query(query)
    logger.info(f"Validación en Athena finalizada con éxito. QueryExecutionId: {query_id}")
    return {"athena_query_id": query_id, "status": "VERIFIED"}


def task_log_final_status(**context):
    """Paso 9: Registro y auditoría del estado final del procesamiento por lote."""
    ti = context["task_instance"]
    run_id = ti.xcom_pull(task_ids="task_extract_to_bronze", key="pipeline_run_id")
    bronze_res = ti.xcom_pull(task_ids="task_extract_to_bronze", key="bronze_results")
    silver_res = ti.xcom_pull(task_ids="task_process_silver", key="silver_summary")

    summary_log = {
        "run_id": run_id,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "bronze_status": bronze_res,
        "silver_summary": silver_res,
        "pipeline_state": "COMPLETED_SUCCESSFULLY"
    }
    logger.info(f"RESUMEN FINAL DEL LOTE:\n{json.dumps(summary_log, indent=2)}")
    return summary_log


# -----------------------------------------------------------------------------
# Definición del DAG
# -----------------------------------------------------------------------------

with DAG(
    dag_id="rss_datalake_eltiempo_pipeline",
    default_args=default_args,
    description="Pipeline ETL de Data Lake medallón para noticias RSS de El Tiempo con AWS Comprehend y Athena",
    schedule_interval="*/30 * * * *", # Ejecución programada cada 30 minutos
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1, # Control de concurrencia: evita escrituras conflictivas simultáneas
    params={
        "reprocess_run_id": Param(
            "", 
            type="string", 
            description="Si deseas reprocesar un lote existente desde Bronze sin consultar los RSS, indica aquí su run_id."
        )
    },
    tags=["datalake", "medallion", "comprehend", "athena", "glue", "el_tiempo"],
) as dag:

    t1_validate = PythonOperator(
        task_id="task_validate_config",
        python_callable=task_validate_config,
    )

    t2_extract = PythonOperator(
        task_id="task_extract_to_bronze",
        python_callable=task_extract_to_bronze,
    )

    t3_4_5_silver = PythonOperator(
        task_id="task_process_silver",
        python_callable=task_clean_validate_enrich_silver,
    )

    t6_gold = PythonOperator(
        task_id="task_build_gold",
        python_callable=task_build_gold,
    )

    t7_glue = PythonOperator(
        task_id="task_sync_glue",
        python_callable=task_sync_glue_catalog,
    )

    t8_athena = PythonOperator(
        task_id="task_validate_athena",
        python_callable=task_validate_athena,
    )

    t9_summary = PythonOperator(
        task_id="task_log_final_status",
        python_callable=task_log_final_status,
    )

    # Dependencias explícitas de extremo a extremo
    t1_validate >> t2_extract >> t3_4_5_silver >> t6_gold >> t7_glue >> t8_athena >> t9_summary
