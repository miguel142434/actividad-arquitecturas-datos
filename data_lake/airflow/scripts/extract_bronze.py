import hashlib
import json
import logging
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
import requests
import boto3
from config import DATALAKE_BUCKET, AWS_REGION, RSS_FEEDS, HTTP_HEADERS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("BronzeExtractor")

s3_client = boto3.client("s3", region_name=AWS_REGION)

def extract_feed_data(run_id: str = None, reprocess_run_id: str = None, execution_date_str: str = None):
    """
    Extrae feeds RSS y los almacena en la capa Bronze en S3 con sus metadatos.
    Si se suministra reprocess_run_id, utiliza los archivos ya existentes en S3 sin consultar la web.
    """
    utc_now = datetime.now(timezone.utc)
    if not run_id:
        run_id = utc_now.strftime("%Y%m%dT%H%M%SZ")
    
    date_partition = execution_date_str if execution_date_str else utc_now.strftime("%Y-%m-%d")
    results = []

    for feed_cfg in RSS_FEEDS:
        source_id = f"{feed_cfg['source']}_{feed_cfg['section']}"
        s3_prefix = f"bronze/source={source_id}/ingestion_date={date_partition}/run_id={run_id}"
        raw_s3_key = f"{s3_prefix}/raw_feed.xml"
        manifest_s3_key = f"{s3_prefix}/manifest.json"

        # Caso 1: Reprocesamiento desde Bronze
        if reprocess_run_id:
            old_s3_prefix = f"bronze/source={source_id}/ingestion_date={date_partition}/run_id={reprocess_run_id}"
            old_raw_key = f"{old_s3_prefix}/raw_feed.xml"
            logger.info(f"Modo Reprocesamiento: Consultando S3 existente s3://{DATALAKE_BUCKET}/{old_raw_key}")
            try:
                response = s3_client.get_object(Bucket=DATALAKE_BUCKET, Key=old_raw_key)
                content_bytes = response["Body"].read()
                results.append({
                    "source": source_id,
                    "section": feed_cfg["section"],
                    "url": feed_cfg["url"],
                    "s3_bucket": DATALAKE_BUCKET,
                    "s3_raw_key": old_raw_key,
                    "run_id": reprocess_run_id,
                    "is_reprocessing": True,
                    "status": "SUCCESS"
                })
                continue
            except Exception as e:
                logger.error(f"Error al recuperar lote previo s3://{DATALAKE_BUCKET}/{old_raw_key}: {e}")
                results.append({
                    "source": source_id,
                    "status": "FAILED",
                    "error": str(e)
                })
                continue

        # Caso 2: Nueva extracción desde Internet
        logger.info(f"Consultando feed {feed_cfg['name']} en {feed_cfg['url']}")
        http_status = None
        content_hash = None
        records_count = 0
        error_msg = None

        try:
            resp = requests.get(feed_cfg["url"], headers=HTTP_HEADERS, timeout=20)
            http_status = resp.status_code

            if resp.status_code != 200:
                raise ValueError(f"HTTP Status no exitoso: {resp.status_code}")

            content_bytes = resp.content
            if not content_bytes or len(content_bytes.strip()) == 0:
                raise ValueError("Respuesta vacía recibida del servidor RSS")

            content_hash = hashlib.sha256(content_bytes).hexdigest()

            # Validación de XML bien formado
            try:
                root = ET.fromstring(content_bytes)
                # Contar elementos <item>
                items = root.findall(".//item")
                records_count = len(items)
            except ET.ParseError as pe:
                raise ValueError(f"XML malformado detectado: {pe}")

            # Subir a S3 Raw Feed
            s3_client.put_object(
                Bucket=DATALAKE_BUCKET,
                Key=raw_s3_key,
                Body=content_bytes,
                ContentType="application/xml"
            )

            # Metadata del lote
            manifest = {
                "run_id": run_id,
                "media": "El Tiempo",
                "source": feed_cfg["source"],
                "section": feed_cfg["section"],
                "url": feed_cfg["url"],
                "ingestion_timestamp_utc": utc_now.isoformat(),
                "http_status": http_status,
                "content_hash": content_hash,
                "s3_bucket": DATALAKE_BUCKET,
                "s3_raw_key": raw_s3_key,
                "records_detected": records_count,
                "is_reprocessing": False
            }

            s3_client.put_object(
                Bucket=DATALAKE_BUCKET,
                Key=manifest_s3_key,
                Body=json.dumps(manifest, indent=2),
                ContentType="application/json"
            )

            logger.info(f"Guardado exitoso en Bronze: s3://{DATALAKE_BUCKET}/{raw_s3_key} ({records_count} items)")
            results.append({
                "source": source_id,
                "section": feed_cfg["section"],
                "url": feed_cfg["url"],
                "s3_bucket": DATALAKE_BUCKET,
                "s3_raw_key": raw_s3_key,
                "run_id": run_id,
                "records_count": records_count,
                "is_reprocessing": False,
                "status": "SUCCESS"
            })

        except Exception as e:
            logger.error(f"Fallo al extraer {feed_cfg['url']}: {e}")
            results.append({
                "source": source_id,
                "section": feed_cfg["section"],
                "url": feed_cfg["url"],
                "http_status": http_status,
                "status": "FAILED",
                "error": str(e)
            })

    return results

if __name__ == "__main__":
    res = extract_feed_data()
    print(json.dumps(res, indent=2))
