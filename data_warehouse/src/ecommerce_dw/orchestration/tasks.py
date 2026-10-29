"""Operaciones AWS usadas por los DAGs mediante el entorno externo de dbt."""

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import logging
import os
from pathlib import Path
import shutil
import tempfile
import uuid

import boto3
from botocore.config import Config

from ecommerce_dw.ingestion.batch_store import BatchStore, encode, sha256, freeze_package, extract_batch
from ecommerce_dw.ingestion.extract_sources import extract_mysql, extract_documentdb, ENTITIES
from ecommerce_dw.sources.mysql_connection import connect_mysql
from ecommerce_dw.sources.documentdb_connection import connect_documentdb
from ecommerce_dw.warehouse.connection import connect_redshift
from ecommerce_dw.warehouse.load_raw import load_batch, mark_validated, SCHEMAS
from ecommerce_dw.warehouse.cli import LOCK_FILE
from ecommerce_dw.transformations.dbt_runner import run_dbt
from .spec import normalize_spec

LOGGER = logging.getLogger(__name__)
WORKSPACE = Path(os.getenv('EXTRACT_WORKSPACE', '/opt/warehouse/extracts'))


def store_client():
    bucket = os.getenv('S3_RAW_BUCKET')
    if not bucket:
        raise ValueError('Configurar S3_RAW_BUCKET.')
    client = boto3.Session(region_name='us-east-1').client('s3', region_name='us-east-1',
        config=Config(retries={'mode': 'standard', 'max_attempts': 3}, connect_timeout=10, read_timeout=60))
    return BatchStore(client, bucket)


@contextmanager
def locked():
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_FILE.open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def check_manifest_spec(manifest, spec):
    if any(manifest[key] != value for key, value in spec.items()):
        raise ValueError('La selección no coincide con el lote ya publicado.')


def validate_request(store, spec):
    request, published = store.claim(spec['batch_id'], spec['source_batch_id'], spec['kind'])
    if published:
        check_manifest_spec(request, spec)
        store.verify(request)
    return request, published


def event(store, spec, status, details=None):
    safe = details or {}
    # Solo identificadores y estado; nunca almacenar excepción, entorno ni credenciales.
    permitted = {'dag_id', 'run_id', 'task_id', 'try_number', 'rows'}
    safe = {key: value for key, value in safe.items() if key in permitted}
    key = f"control/runs/{spec['batch_id']}/{uuid.uuid4().hex}.json"
    store.immutable(key, encode({'batch_id': spec['batch_id'], 'status': status,
        'at': datetime.now(timezone.utc).isoformat(), **safe}))


def validate_connections(store, spec):
    _, published = validate_request(store, spec)
    # La repetición o subida pendiente de paquete congelado no requiere fuentes vivas.
    if not published and not (WORKSPACE/spec['batch_id']).exists():
        parts = WORKSPACE/'.airflow'/spec['batch_id']
        if not (parts/'mysql/part.json').exists():
            connection = connect_mysql()
            connection.close()
        if spec['kind'] != 'changes' and not (parts/'documentdb/part.json').exists():
            client = connect_documentdb()
            try:
                client.admin.command('ping')
            finally:
                client.close()
    connection = connect_redshift()
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            if cursor.fetchone()[0] != 1:
                raise ValueError('No se pudo validar Redshift.')
    finally:
        connection.close()
    event(store, spec, 'STARTED')
    return spec


def extract_source(store, spec, source):
    request, published = validate_request(store, spec)
    if published or (WORKSPACE/spec['batch_id']).exists():
        return {'source': source, 'reused': True}
    directory = WORKSPACE/'.airflow'/spec['batch_id']/source
    marker = directory/'part.json'
    if marker.exists():
        return {'source': source, 'reused': True}
    directory.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f'.{source}-', dir=directory.parent))
    try:
        checkpoint = {}
        if source == 'mysql':
            previous = {}
            if request['parent'] and spec['kind'] != 'reconcile':
                previous = store.verify(store.checked_manifest(request['parent']))
            entities, checkpoint = extract_mysql(temporary, spec['source_batch_id'], previous,
                                                   changes_only=spec['kind'] == 'changes')
        else:
            entities = extract_documentdb(temporary, spec['source_batch_id'], changes_only=spec['kind'] == 'changes')
        hashes = {entry['file']: sha256((temporary/entry['file']).read_bytes()) for entry in entities.values()}
        (temporary/'part.json').write_bytes(encode({'request': request, 'entities': entities,
                                                    'checkpoint': checkpoint, 'hashes': hashes}))
        temporary.rename(directory)
    finally:
        if temporary.exists(): shutil.rmtree(temporary)
    return {'source': source, 'rows': {name: value['rows'] for name, value in entities.items()}}


def publish(store, spec):
    request, published = validate_request(store, spec)
    package = WORKSPACE/spec['batch_id']
    if not published and not package.exists():
        temporary = Path(tempfile.mkdtemp(prefix=f".{spec['batch_id']}-", dir=WORKSPACE))
        try:
            entities, checkpoint = {}, {}
            for source in ('mysql', 'documentdb'):
                directory = WORKSPACE/'.airflow'/spec['batch_id']/source
                part = json.loads((directory/'part.json').read_bytes())
                if part['request'] != request:
                    raise ValueError('La parte extraída no corresponde a la reserva del lote.')
                for entity, entry in part['entities'].items():
                    if entity not in ENTITIES or entry['file'] != entity.replace('/', '_')+'.csv':
                        raise ValueError('Entidad o archivo de extracción inválido.')
                    body = (directory/entry['file']).read_bytes()
                    if sha256(body) != part['hashes'][entry['file']]:
                        raise ValueError('Una parte local fue modificada; no publicar.')
                    (temporary/entry['file']).write_bytes(body)
                    entities[entity] = entry
                checkpoint.update(part['checkpoint'])
            if set(entities) != set(ENTITIES):
                raise ValueError('Se requieren las seis entidades para publicar.')
            freeze_package(request, entities, checkpoint, temporary, package)
        finally:
            if temporary.exists(): shutil.rmtree(temporary)
    manifest = extract_batch(store, spec['batch_id'], spec['source_batch_id'], WORKSPACE, kind=spec['kind'])
    event(store, spec, 'EXTRACTED', {'rows': {key: value['rows'] for key, value in manifest['entities'].items()}})
    return {'batch_id': spec['batch_id'], 'status': 'EXTRACTED'}


def sql_status(batch_id):
    connection = connect_redshift()
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT status FROM control.batches WHERE batch_id=%s', (batch_id,))
            value = cursor.fetchone()
            if value is None: raise ValueError('El lote no se ha cargado a raw.')
            return value[0]
    finally:
        connection.close()


def verify_raw_counts(store, spec):
    manifest = store.checked_manifest(spec['batch_id'])
    check_manifest_spec(manifest, spec)
    store.verify(manifest)
    if sql_status(spec['batch_id']) == 'VALIDATED':
        return {'status': 'VALIDATED', 'reused': True}
    connection = connect_redshift()
    try:
        with connection.cursor() as cursor:
            for entity, (table, _) in SCHEMAS.items():
                cursor.execute(f'SELECT COUNT(*) FROM "raw".{table} WHERE _batch_id=%s', (spec['batch_id'],))
                if cursor.fetchone()[0] != manifest['entities'][entity]['rows']:
                    raise ValueError('Conteo raw del lote distinto a la extracción.')
    finally:
        connection.close()
    return {'batch_id': spec['batch_id'], 'status': 'LOADED'}


DBT_STEPS = {'dbt_deps': ('deps', None), 'dbt_seed': ('seed', None),
    'dbt_run_intermediate': ('run', 'path:models/intermediate'),
    'dbt_run_quarantine': ('run', 'path:models/quarantine'), 'dbt_snapshot': ('snapshot', None),
    'dbt_run_marts': ('run', 'path:models/marts'), 'dbt_test': ('test', None)}


def execute_step(step, spec):
    spec = normalize_spec(spec)
    store = store_client()
    LOGGER.info('batch_id=%s step=%s', spec['batch_id'], step)
    try:
        if step in ('mysql', 'documentdb'):
            return extract_source(store, spec, step)
        with locked():
            if step == 'refresh_spice':
                dataset = os.getenv('QUICKSIGHT_DATASET_ID')
                if not dataset:
                    return {'batch_id': spec['batch_id'], 'status': 'DISABLED'}
                from ecommerce_dw.consumption.refresh import refresh_batch
                account = os.environ['QUICKSIGHT_ACCOUNT_ID']
                client = boto3.Session(region_name='us-east-1').client('quicksight', region_name='us-east-1')
                return refresh_batch(store, spec['batch_id'], account, dataset, client)
            if step == 'validate_request':
                validate_request(store, spec)
                return spec
            if step == 'validate_connections': return validate_connections(store, spec)
            if step == 'publish': return publish(store, spec)
            manifest = store.checked_manifest(spec['batch_id'])
            check_manifest_spec(manifest, spec)
            if step == 'load_raw':
                result = load_batch(store, spec['batch_id'], os.environ['REDSHIFT_COPY_ROLE_ARN'])
                event(store, spec, result)
                return {'batch_id': spec['batch_id'], 'status': result}
            if step == 'verify_raw_counts': return verify_raw_counts(store, spec)
            if step in DBT_STEPS:
                if sql_status(spec['batch_id']) != 'VALIDATED':
                    command, selector = DBT_STEPS[step]
                    run_dbt(command, selector)
                return {'batch_id': spec['batch_id'], 'step': step}
            if step == 'complete':
                if sql_status(spec['batch_id']) != 'VALIDATED': mark_validated(spec['batch_id'])
                state, _ = store.state()
                if state['accepted'] == spec['batch_id'] or (state['pending'] and state['pending']['batch_id'] == spec['batch_id']):
                    store.accept(spec['batch_id'])
                event(store, spec, 'VALIDATED')
                return {'batch_id': spec['batch_id'], 'status': 'VALIDATED'}
            raise ValueError('Tarea desconocida.')
    except Exception as error:
        # Airflow registra esta excepción sin incluir URI ni mensajes del driver.
        raise RuntimeError(f"batch_id={spec['batch_id']} step={step} failed={type(error).__name__}") from None
