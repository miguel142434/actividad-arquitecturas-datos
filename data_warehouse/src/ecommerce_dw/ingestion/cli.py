"""CLI de extracción y reproceso; no crea infraestructura ni carga Redshift."""

import argparse
import os

import boto3
from botocore.config import Config

from .batch_store import BatchStore, extract_batch, replay_batch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bucket", default=os.getenv("S3_RAW_BUCKET"))
    parser.add_argument("--profile", help="Perfil local opcional; en EC2 se usa su rol sin claves estáticas.")
    commands = parser.add_subparsers(dest="command", required=True)
    extract = commands.add_parser("extract")
    extract.add_argument("--batch-id", required=True)
    selection = extract.add_mutually_exclusive_group(required=True)
    selection.add_argument("--initial", action="store_true")
    selection.add_argument("--reconcile", action="store_true", help="Foto completa explícita para conciliación de eliminaciones/correcciones.")
    selection.add_argument("--source-batch-id", type=int)
    selection.add_argument("--changes-only", action="store_true", help="Solo cambios de clientes/productos (escenario SCD2).")
    extract.add_argument("--workspace", default=os.getenv("EXTRACT_WORKSPACE", "warehouse/extracts"))
    replay = commands.add_parser("replay")
    replay.add_argument("--batch-id", required=True)
    replay.add_argument("--directory", default="warehouse/replay")
    args = parser.parse_args()
    if not args.bucket:
        parser.error("Definir S3_RAW_BUCKET o --bucket.")
    session = boto3.Session(profile_name=args.profile, region_name="us-east-1")
    client = session.client("s3", region_name="us-east-1", config=Config(
        retries={"mode": "standard", "max_attempts": 3}, connect_timeout=10, read_timeout=60))
    store = BatchStore(client, args.bucket)
    old_mask = os.umask(0o077)
    try:
        if args.command == "extract":
            kind = "reconcile" if args.reconcile else "changes" if args.changes_only else "initial" if args.initial else "incremental"
            manifest = extract_batch(store, args.batch_id, args.source_batch_id, args.workspace, kind=kind)
        else:
            manifest = replay_batch(store, args.batch_id, args.directory)
    except Exception as error:
        # No volcar mensajes del driver, URI, entorno ni credenciales a los logs.
        code = type(error).__name__
        if hasattr(error, "response"):
            code = error.response.get("Error", {}).get("Code", code)
        raise SystemExit(f"Extracción/reproceso falló ({code}); el lote no se confirmó. "
                         "Conservar el workspace y revisar permisos, conectividad y selección del lote.") from None
    finally:
        os.umask(old_mask)
    print(f"Lote {manifest['batch_id']}: EXTRACTED; no implica carga ni validación del warehouse.")
    for entity, info in manifest["entities"].items():
        print(f"{entity}: {info['rows']} registros")


if __name__ == "__main__":
    main()
