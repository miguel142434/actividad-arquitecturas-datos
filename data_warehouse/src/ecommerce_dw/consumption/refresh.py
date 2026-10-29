"""Actualiza SPICE después de calidad; un fallo no revierte el warehouse validado."""
from contextlib import closing
from datetime import datetime, timezone
from decimal import Decimal
import argparse
import json
import os
import time

from botocore.exceptions import ClientError
from ecommerce_dw.ingestion.batch_store import encode
from ecommerce_dw.warehouse.connection import connect_redshift
from .assets import VALIDATION_SQL


def warehouse_cut(connection_factory, batch_id):
    with closing(connection_factory()) as connection:
        with connection.cursor() as cursor:
            cursor.execute('SELECT status FROM control.batches WHERE batch_id=%s', (batch_id,))
            if cursor.fetchone() != ('VALIDATED',):
                raise ValueError('SPICE requiere un lote SQL VALIDATED.')
            cursor.execute(VALIDATION_SQL, (None, None))
            rows, amount = cursor.fetchone()
    return int(rows), str(Decimal(amount).quantize(Decimal('0.01')))


def refresh_batch(store, batch_id, account, dataset, client,
                  connection_factory=connect_redshift, sleep=time.sleep, max_polls=120):
    state, _ = store.state()
    if state['pending']:
        raise ValueError('No refrescar SPICE mientras exista un lote pendiente.')
    if state['accepted'] != batch_id:
        return {'batch_id': batch_id, 'status': 'SKIPPED_OLD_BATCH'}
    expected = warehouse_cut(connection_factory, batch_id)
    receipt_key = f'control/consumption/{dataset}/{batch_id}.json'
    receipt, _ = store.json(receipt_key)
    if receipt:
        if (receipt['rows'], receipt['sql_expected_total']) != expected:
            raise ValueError('El warehouse difiere del corte previamente publicado en SPICE.')
        return receipt
    # Los reintentos reutilizan una ingestión en curso o completada. Solo después
    # de un fallo terminal se usa el siguiente ID; como máximo tres por lote.
    for attempt in range(1, 4):
        ingestion_id = f'batch-{batch_id}-{attempt}'
        request = {'AwsAccountId': account, 'DataSetId': dataset, 'IngestionId': ingestion_id}
        try:
            ingestion = client.describe_ingestion(**request)['Ingestion']
        except ClientError as error:
            detail = error.response['Error']
            # DescribeIngestion devuelve también este error para un ID nuevo
            # (comprobado en AWS). No ocultar otros parámetros inválidos.
            missing = detail['Code'] == 'ResourceNotFoundException' or (
                detail['Code'] == 'InvalidParameterValueException' and
                detail.get('Message', '').startswith(
                    f'No record with datasetId {dataset} and ingestionId {ingestion_id} '))
            if not missing:
                raise
            client.create_ingestion(**request, IngestionType='FULL_REFRESH')
            ingestion = None
            break
        if ingestion['IngestionStatus'] not in ('FAILED','CANCELLED'):
            break
    else:
        raise RuntimeError('SPICE agotó los tres intentos de este lote.')
    for _ in range(max_polls):
        if ingestion is None:
            ingestion = client.describe_ingestion(**request)['Ingestion']
        status = ingestion['IngestionStatus']
        if status == 'COMPLETED':
            break
        if status in ('FAILED','CANCELLED'):
            raise RuntimeError('La ingestión SPICE falló; conservar el warehouse y reintentar solo el consumo.')
        sleep(5)
        ingestion = None
    else:
        raise TimeoutError('SPICE sigue en curso; reintentar consulta del mismo ID.')
    rows = ingestion['RowInfo']['RowsIngested']
    if rows != expected[0] or ingestion['RowInfo']['RowsDropped'] != 0:
        raise ValueError('SPICE no conserva todas las filas del corte validado.')
    current, _ = store.state()
    if current != state or warehouse_cut(connection_factory, batch_id) != expected:
        raise ValueError('Cambió el corte durante la ingestión; no confirmar consumo.')
    receipt = {'batch_id': batch_id, 'dataset_id': dataset, 'ingestion_id': ingestion_id,
        'status': 'COMPLETED', 'rows': rows, 'rows_dropped': 0,
        'sql_expected_total': expected[1], 'filter': 'Todas las categorías',
        'confirmed_at_utc': datetime.now(timezone.utc).isoformat(),
        'note': 'Total SQL para contrastar con el KPI visible; el API de ingestión no devuelve SUM de SPICE.'}
    store.immutable(receipt_key, encode(receipt))
    return receipt


def main():
    from ecommerce_dw.orchestration.tasks import execute_step
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch-id', required=True)
    args = parser.parse_args()
    # kind no se usa para reextraer: este comando solo opera sobre un lote validado.
    result = execute_step('refresh_spice', {'batch_id': args.batch_id, 'kind': 'initial', 'source_batch_id': None})
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
