import logging
import time
import boto3
from config import DATALAKE_BUCKET, AWS_REGION, GLUE_DATABASE, ATHENA_WORKGROUP

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("GlueCatalogSync")

athena_client = boto3.client("athena", region_name=AWS_REGION)

# Sentencias DDL para registrar las tablas de Silver y Gold en Glue / Athena
DDL_STATEMENTS = [
    # 1. Silver News
    f"""
    CREATE EXTERNAL TABLE IF NOT EXISTS {GLUE_DATABASE}.silver_news (
        news_id STRING,
        source STRING,
        media STRING,
        section STRING,
        title STRING,
        description STRING,
        link STRING,
        pub_date_original STRING,
        pub_date_utc STRING,
        content_hash STRING,
        bronze_source_file STRING,
        run_id STRING,
        is_active BOOLEAN
    )
    PARTITIONED BY (dt STRING)
    STORED AS PARQUET
    LOCATION 's3://{DATALAKE_BUCKET}/silver/news/'
    tblproperties ("parquet.compression"="SNAPPY");
    """,

    # 2. Silver News Entities
    f"""
    CREATE EXTERNAL TABLE IF NOT EXISTS {GLUE_DATABASE}.silver_news_entities (
        news_id STRING,
        entity_text STRING,
        entity_type STRING,
        confidence_score DOUBLE,
        language STRING,
        analyzed_text_hash STRING,
        analyzed_at_utc STRING,
        run_id STRING
    )
    PARTITIONED BY (dt STRING)
    STORED AS PARQUET
    LOCATION 's3://{DATALAKE_BUCKET}/silver/news_entities/'
    tblproperties ("parquet.compression"="SNAPPY");
    """,

    # 3. Silver News Key Phrases
    f"""
    CREATE EXTERNAL TABLE IF NOT EXISTS {GLUE_DATABASE}.silver_news_key_phrases (
        news_id STRING,
        key_phrase STRING,
        confidence_score DOUBLE,
        language STRING,
        analyzed_text_hash STRING,
        analyzed_at_utc STRING,
        run_id STRING
    )
    PARTITIONED BY (dt STRING)
    STORED AS PARQUET
    LOCATION 's3://{DATALAKE_BUCKET}/silver/news_key_phrases/'
    tblproperties ("parquet.compression"="SNAPPY");
    """,

    # 4. Gold News By Day
    f"""
    CREATE EXTERNAL TABLE IF NOT EXISTS {GLUE_DATABASE}.gold_news_by_day (
        media STRING,
        section STRING,
        total_news BIGINT,
        run_id STRING
    )
    PARTITIONED BY (dt STRING)
    STORED AS PARQUET
    LOCATION 's3://{DATALAKE_BUCKET}/gold/gold_news_by_day/'
    tblproperties ("parquet.compression"="SNAPPY");
    """,

    # 5. Gold Top Entities
    f"""
    CREATE EXTERNAL TABLE IF NOT EXISTS {GLUE_DATABASE}.gold_top_entities (
        entity_text STRING,
        entity_type STRING,
        distinct_news_count BIGINT,
        avg_confidence DOUBLE,
        run_id STRING
    )
    PARTITIONED BY (dt STRING)
    STORED AS PARQUET
    LOCATION 's3://{DATALAKE_BUCKET}/gold/gold_top_entities/'
    tblproperties ("parquet.compression"="SNAPPY");
    """,

    # 6. Gold Top Key Phrases
    f"""
    CREATE EXTERNAL TABLE IF NOT EXISTS {GLUE_DATABASE}.gold_top_key_phrases (
        section STRING,
        key_phrase STRING,
        frequency_count BIGINT,
        avg_confidence DOUBLE,
        run_id STRING
    )
    PARTITIONED BY (dt STRING)
    STORED AS PARQUET
    LOCATION 's3://{DATALAKE_BUCKET}/gold/gold_top_key_phrases/'
    tblproperties ("parquet.compression"="SNAPPY");
    """,

    # 7. Gold Entity Trend
    f"""
    CREATE EXTERNAL TABLE IF NOT EXISTS {GLUE_DATABASE}.gold_entity_trend (
        entity_text STRING,
        entity_type STRING,
        distinct_news_count BIGINT,
        run_id STRING
    )
    PARTITIONED BY (dt STRING)
    STORED AS PARQUET
    LOCATION 's3://{DATALAKE_BUCKET}/gold/gold_entity_trend/'
    tblproperties ("parquet.compression"="SNAPPY");
    """
]

TABLE_NAMES = [
    "silver_news",
    "silver_news_entities",
    "silver_news_key_phrases",
    "gold_news_by_day",
    "gold_top_entities",
    "gold_top_key_phrases",
    "gold_entity_trend"
]

def run_athena_query(query_str: str):
    """Ejecuta una consulta en Athena y espera a que finalice."""
    response = athena_client.start_query_execution(
        QueryString=query_str,
        QueryExecutionContext={"Database": GLUE_DATABASE},
        WorkGroup=ATHENA_WORKGROUP,
        ResultConfiguration={
            "OutputLocation": f"s3://{DATALAKE_BUCKET}/athena-results/"
        }
    )
    query_id = response["QueryExecutionId"]

    while True:
        status_resp = athena_client.get_query_execution(QueryExecutionId=query_id)
        state = status_resp["QueryExecution"]["Status"]["State"]
        if state in ["SUCCEEDED"]:
            return query_id
        elif state in ["FAILED", "CANCELLED"]:
            reason = status_resp["QueryExecution"]["Status"].get("StateChangeReason", "Unknown")
            raise RuntimeError(f"Athena query {query_id} falló ({state}): {reason}")
        time.sleep(1.5)

def sync_glue_catalog():
    """Crea las tablas en Glue y actualiza las particiones usando MSCK REPAIR TABLE."""
    logger.info(f"Sincronizando esquemas de tablas en AWS Glue Data Catalog ({GLUE_DATABASE})...")
    
    # 1. Crear tablas si no existen
    for ddl in DDL_STATEMENTS:
        logger.info(f"Ejecutando DDL en Athena...")
        run_athena_query(ddl)

    # 2. Descubrir y registrar nuevas particiones
    for tbl in TABLE_NAMES:
        repair_sql = f"MSCK REPAIR TABLE {GLUE_DATABASE}.{tbl};"
        logger.info(f"Actualizando particiones para {tbl}...")
        try:
            run_athena_query(repair_sql)
        except Exception as e:
            logger.warning(f"Aviso actualizando particiones de {tbl}: {e}")

    logger.info("Sincronización de Glue Data Catalog completada.")
    return {"status": "SUCCESS"}

if __name__ == "__main__":
    sync_glue_catalog()
