import hashlib
import io
import json
import logging
import re
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
import boto3
import pandas as pd
from config import DATALAKE_BUCKET, AWS_REGION, RSS_FEEDS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("SilverProcessor")

s3_client = boto3.client("s3", region_name=AWS_REGION)
comprehend_client = boto3.client("comprehend", region_name=AWS_REGION)

def clean_html(text: str) -> str:
    """Elimina etiquetas HTML y limpia espacios redundantes."""
    if not text:
        return ""
    # Remover etiquetas HTML
    clean = re.sub(r"<[^>]+>", " ", text)
    # Limpiar entidades HTML comunes
    clean = clean.replace("&nbsp;", " ").replace("&amp;", "&").replace("&quot;", '"').replace("&apos;", "'")
    return " ".join(clean.split())

def parse_date_to_utc(date_str: str) -> datetime:
    """Normaliza fechas RFC 822 / RSS a objeto datetime UTC."""
    if not date_str:
        return None
    try:
        dt = parsedate_to_datetime(date_str)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None

def get_comprehend_annotations(text: str, language: str = "es"):
    """
    Invoca Amazon Comprehend para extraer personas, organizaciones, ubicaciones y frases clave.
    Controla el límite de tamaño de texto (máximo 5000 bytes UTF-8).
    """
    if not text or len(text.strip()) == 0:
        return [], []

    # Ajuste de tamaño por el límite de Comprehend (5000 bytes)
    encoded = text.encode("utf-8")
    if len(encoded) > 4800:
        text = encoded[:4800].decode("utf-8", "ignore")

    entities = []
    key_phrases = []

    try:
        # 1. Extracción de entidades
        ent_resp = comprehend_client.detect_entities(Text=text, LanguageCode=language)
        for ent in ent_resp.get("Entities", []):
            etype = ent.get("Type")
            if etype in ["PERSON", "ORGANIZATION", "LOCATION"]:
                entities.append({
                    "text": ent.get("Text").strip(),
                    "type": etype,
                    "score": float(ent.get("Score", 0.0))
                })

        # 2. Extracción de frases clave
        kp_resp = comprehend_client.detect_key_phrases(Text=text, LanguageCode=language)
        for kp in kp_resp.get("KeyPhrases", []):
            phrase = kp.get("Text").strip()
            if phrase:
                key_phrases.append({
                    "text": phrase,
                    "score": float(kp.get("Score", 0.0))
                })

    except Exception as e:
        logger.error(f"Error invocando Amazon Comprehend: {e}")

    return entities, key_phrases

def get_existing_silver_news():
    """Consulta las noticias ya existentes en Silver en S3 para deduplicación entre lotes."""
    paginator = s3_client.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket=DATALAKE_BUCKET, Prefix="silver/news/")
    existing = {}
    for page in pages:
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith(".parquet"):
                try:
                    resp = s3_client.get_object(Bucket=DATALAKE_BUCKET, Key=key)
                    df = pd.read_parquet(io.BytesIO(resp["Body"].read()), columns=["news_id", "content_hash"])
                    for _, row in df.iterrows():
                        existing[row["news_id"]] = row["content_hash"]
                except Exception as e:
                    logger.warning(f"Error leyendo parquet previo {key}: {e}")
    return existing

def process_bronze_to_silver(run_id: str, date_partition: str = None, comprehension_cache: dict = None):
    """
    Lee archivos Bronze de S3, limpia, valida, deduplica entre lotes, enriquece con Comprehend
    y persiste tablas Parquet en la capa Silver de S3.
    """
    if comprehension_cache is None:
        comprehension_cache = {}

    utc_now = datetime.now(timezone.utc)
    if not date_partition:
        date_partition = utc_now.strftime("%Y-%m-%d")

    # Recuperar histórico de noticias vigentes en Silver para deduplicación entre lotes
    existing_news = get_existing_silver_news()
    logger.info(f"Noticias previas registradas en Silver: {len(existing_news)}")

    news_rows = []
    entities_rows = []
    key_phrases_rows = []
    quarantine_rows = []
    seen_guid_in_batch = set()

    for feed_cfg in RSS_FEEDS:
        source_id = f"{feed_cfg['source']}_{feed_cfg['section']}"
        s3_key = f"bronze/source={source_id}/ingestion_date={date_partition}/run_id={run_id}/raw_feed.xml"

        logger.info(f"Procesando Bronze s3://{DATALAKE_BUCKET}/{s3_key}")
        try:
            resp = s3_client.get_object(Bucket=DATALAKE_BUCKET, Key=s3_key)
            raw_xml = resp["Body"].read()
        except Exception as e:
            logger.warning(f"No se encontró archivo bronze para {source_id} en run {run_id}: {e}")
            continue

        try:
            root = ET.fromstring(raw_xml)
        except Exception as e:
            quarantine_rows.append({
                "source": source_id,
                "bronze_s3_key": s3_key,
                "reason": f"XML malformado: {str(e)}",
                "timestamp": utc_now.isoformat()
            })
            continue

        items = root.findall(".//item")
        for item in items:
            raw_guid = item.findtext("guid")
            raw_title = item.findtext("title")
            raw_link = item.findtext("link")
            raw_desc = item.findtext("description")
            raw_pub_date = item.findtext("pubDate")

            cleaned_title = clean_html(raw_title)
            cleaned_desc = clean_html(raw_desc)
            cleaned_link = (raw_link or "").strip()

            # Validación de campos obligatorios
            if not cleaned_title or not cleaned_link:
                quarantine_rows.append({
                    "source": source_id,
                    "bronze_s3_key": s3_key,
                    "reason": "Campo obligatorio ausente (title o link)",
                    "raw_title": raw_title,
                    "raw_link": raw_link,
                    "timestamp": utc_now.isoformat()
                })
                continue

            # Determinación de identificador único (GUID con fallback al link)
            news_id = (raw_guid or "").strip()
            if not news_id:
                news_id = hashlib.sha256(cleaned_link.encode("utf-8")).hexdigest()

            # Deduplicación dentro del lote
            if news_id in seen_guid_in_batch:
                continue
            seen_guid_in_batch.add(news_id)

            # Normalización de fecha a UTC
            pub_dt_utc = parse_date_to_utc(raw_pub_date)
            pub_date_str = pub_dt_utc.strftime("%Y-%m-%d %H:%M:%S") if pub_dt_utc else None
            partition_date = pub_dt_utc.strftime("%Y-%m-%d") if pub_dt_utc else date_partition

            # Hash del contenido textual para detectar cambios
            text_for_analysis = f"{cleaned_title}. {cleaned_desc}".strip()
            content_hash = hashlib.sha256(text_for_analysis.encode("utf-8")).hexdigest()

            # Deduplicación entre lotes: si la noticia ya existe en Silver y no cambió, omitir
            if news_id in existing_news and existing_news[news_id] == content_hash:
                continue

            news_rows.append({
                "news_id": news_id,
                "source": feed_cfg["source"],
                "media": "El Tiempo",
                "section": feed_cfg["section"],
                "title": cleaned_title,
                "description": cleaned_desc,
                "link": cleaned_link,
                "pub_date_original": raw_pub_date,
                "pub_date_utc": pub_date_str,
                "content_hash": content_hash,
                "bronze_source_file": s3_key,
                "run_id": run_id,
                "is_active": True,
                "dt": partition_date
            })

            # Reutilizar caché de Comprehend si el texto ya fue analizado
            if content_hash in comprehension_cache:
                cached_entities, cached_phrases = comprehension_cache[content_hash]
            else:
                cached_entities, cached_phrases = get_comprehend_annotations(text_for_analysis, language="es")
                comprehension_cache[content_hash] = (cached_entities, cached_phrases)

            # Deduplicar entidades por noticia vigente (una fila por entidad distinta detectada)
            unique_entities = set()
            for ent in cached_entities:
                ent_key = (ent["text"].lower(), ent["type"])
                if ent_key not in unique_entities:
                    unique_entities.add(ent_key)
                    entities_rows.append({
                        "news_id": news_id,
                        "entity_text": ent["text"],
                        "entity_type": ent["type"],
                        "confidence_score": ent["score"],
                        "language": "es",
                        "analyzed_text_hash": content_hash,
                        "analyzed_at_utc": utc_now.strftime("%Y-%m-%d %H:%M:%S"),
                        "run_id": run_id,
                        "dt": partition_date
                    })

            # Deduplicar frases clave por noticia vigente (una fila por frase clave distinta)
            unique_phrases = set()
            for kp in cached_phrases:
                kp_norm = kp["text"].lower()
                if kp_norm not in unique_phrases:
                    unique_phrases.add(kp_norm)
                    key_phrases_rows.append({
                        "news_id": news_id,
                        "key_phrase": kp["text"],
                        "confidence_score": kp["score"],
                        "language": "es",
                        "analyzed_text_hash": content_hash,
                        "analyzed_at_utc": utc_now.strftime("%Y-%m-%d %H:%M:%S"),
                        "run_id": run_id,
                        "dt": partition_date
                    })

    # Guardar registros de cuarentena en S3 si existieron
    if quarantine_rows:
        quarantine_key = f"quarantine/date={date_partition}/run_id={run_id}/invalid_records.json"
        s3_client.put_object(
            Bucket=DATALAKE_BUCKET,
            Key=quarantine_key,
            Body=json.dumps(quarantine_rows, indent=2),
            ContentType="application/json"
        )
        logger.info(f"Guardados {len(quarantine_rows)} registros rechazados en s3://{DATALAKE_BUCKET}/{quarantine_key}")

    # Guardar en S3 formato Parquet por partición
    def save_df_to_parquet(df, prefix_name):
        if df.empty:
            return
        for dt_val, group in df.groupby("dt"):
            # Omitir la columna de partición del archivo parquet para que Athena use la estructura de carpetas
            df_to_write = group.drop(columns=["dt"])
            buffer = io.BytesIO()
            df_to_write.to_parquet(buffer, index=False, engine="pyarrow", compression="snappy")
            s3_key = f"silver/{prefix_name}/dt={dt_val}/{prefix_name}_{run_id}.parquet"
            s3_client.put_object(Bucket=DATALAKE_BUCKET, Key=s3_key, Body=buffer.getvalue())
            logger.info(f"Guardado exitoso: s3://{DATALAKE_BUCKET}/{s3_key} ({len(group)} filas)")

    save_df_to_parquet(pd.DataFrame(news_rows), "news")
    save_df_to_parquet(pd.DataFrame(entities_rows), "news_entities")
    save_df_to_parquet(pd.DataFrame(key_phrases_rows), "news_key_phrases")

    return {
        "status": "SUCCESS",
        "processed_news": len(news_rows),
        "processed_entities": len(entities_rows),
        "processed_key_phrases": len(key_phrases_rows),
        "quarantined_count": len(quarantine_rows),
        "run_id": run_id
    }

if __name__ == "__main__":
    import sys
    run_id_arg = sys.argv[1] if len(sys.argv) > 1 else datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    res = process_bronze_to_silver(run_id_arg)
    print(json.dumps(res, indent=2))
