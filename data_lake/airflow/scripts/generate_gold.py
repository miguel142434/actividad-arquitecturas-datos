import io
import json
import logging
from datetime import datetime, timezone
import boto3
import pandas as pd
from config import DATALAKE_BUCKET, AWS_REGION

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("GoldAggregator")

s3_client = boto3.client("s3", region_name=AWS_REGION)

def read_silver_parquet_from_s3(prefix: str):
    """Descarga y concatena todos los archivos Parquet bajo un prefijo Silver."""
    paginator = s3_client.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket=DATALAKE_BUCKET, Prefix=prefix)
    
    dfs = []
    for page in pages:
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith(".parquet"):
                # Extraer partición dt del key si existe (ej. dt=2026-10-22)
                dt_val = None
                for part in key.split("/"):
                    if part.startswith("dt="):
                        dt_val = part.split("=")[1]
                        break
                
                resp = s3_client.get_object(Bucket=DATALAKE_BUCKET, Key=key)
                df_part = pd.read_parquet(io.BytesIO(resp["Body"].read()))
                if dt_val and "dt" not in df_part.columns:
                    df_part["dt"] = dt_val
                dfs.append(df_part)
                
    if dfs:
        return pd.concat(dfs, ignore_index=True)
    return pd.DataFrame()

def save_gold_parquet_to_s3(df: pd.DataFrame, dataset_name: str, run_id: str):
    """Guarda DataFrame en la capa Gold particionado por dt en S3."""
    if df.empty:
        logger.warning(f"Dataset {dataset_name} está vacío. No se escribe en Gold.")
        return
    for dt_val, group in df.groupby("dt"):
        df_to_write = group.drop(columns=["dt"])
        buffer = io.BytesIO()
        df_to_write.to_parquet(buffer, index=False, engine="pyarrow", compression="snappy")
        s3_key = f"gold/{dataset_name}/dt={dt_val}/{dataset_name}.parquet"
        s3_client.put_object(Bucket=DATALAKE_BUCKET, Key=s3_key, Body=buffer.getvalue())
        logger.info(f"Guardado Gold: s3://{DATALAKE_BUCKET}/{s3_key} ({len(group)} filas)")

def generate_gold_aggregates(run_id: str):
    """
    Lee las tablas Silver y construye las 4 agregaciones analíticas requeridas por la guía.
    """
    logger.info(f"Iniciando cálculo de Capa Gold para run_id={run_id}")
    
    # 1. Leer Silver News
    df_news = read_silver_parquet_from_s3("silver/news/")
    if df_news.empty:
        logger.error("No se encontraron datos en silver/news/. Abortando Gold.")
        return {"status": "FAILED", "reason": "No data in silver/news/"}
    
    # Filtrar solo noticias vigentes
    if "is_active" in df_news.columns:
        df_news = df_news[df_news["is_active"] == True]

    # 2. Leer Silver Entities y Key Phrases
    df_entities = read_silver_parquet_from_s3("silver/news_entities/")
    df_phrases = read_silver_parquet_from_s3("silver/news_key_phrases/")

    # Agregación 1: Noticias publicadas por día, medio y sección
    df_news_by_day = df_news.groupby(["dt", "media", "section"])["news_id"].nunique().reset_index()
    df_news_by_day.rename(columns={"news_id": "total_news"}, inplace=True)
    df_news_by_day["run_id"] = run_id
    save_gold_parquet_to_s3(df_news_by_day, "gold_news_by_day", run_id)

    # Agregación 2: Personas, Organizaciones y Lugares que aparecen en más noticias (noticias distintas)
    if not df_entities.empty:
        # Cruce con news para asegurar consistencia
        df_ent_joined = df_entities.merge(df_news[["news_id", "section"]], on="news_id", how="inner")
        
        df_top_entities = df_ent_joined.groupby(["dt", "entity_text", "entity_type"]).agg(
            distinct_news_count=("news_id", "nunique"),
            avg_confidence=("confidence_score", "mean")
        ).reset_index()
        df_top_entities["run_id"] = run_id
        save_gold_parquet_to_s3(df_top_entities, "gold_top_entities", run_id)

        # Agregación 4: Tendencia de presencia de una entidad entre fechas
        df_trend = df_ent_joined.groupby(["dt", "entity_text", "entity_type"])["news_id"].nunique().reset_index()
        df_trend.rename(columns={"news_id": "distinct_news_count"}, inplace=True)
        df_trend["run_id"] = run_id
        save_gold_parquet_to_s3(df_trend, "gold_entity_trend", run_id)

    # Agregación 3: Frases clave más frecuentes por sección
    if not df_phrases.empty:
        df_phr_joined = df_phrases.merge(df_news[["news_id", "section"]], on="news_id", how="inner")
        df_top_phrases = df_phr_joined.groupby(["dt", "section", "key_phrase"]).agg(
            frequency_count=("news_id", "nunique"),
            avg_confidence=("confidence_score", "mean")
        ).reset_index()
        df_top_phrases["run_id"] = run_id
        save_gold_parquet_to_s3(df_top_phrases, "gold_top_key_phrases", run_id)

    logger.info("Capa Gold generada exitosamente.")
    return {"status": "SUCCESS", "run_id": run_id}

if __name__ == "__main__":
    import sys
    run_id_arg = sys.argv[1] if len(sys.argv) > 1 else datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    res = generate_gold_aggregates(run_id_arg)
    print(json.dumps(res, indent=2))
