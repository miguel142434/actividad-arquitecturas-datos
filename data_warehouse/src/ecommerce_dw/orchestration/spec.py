"""Contrato de ejecución sin secretos, reutilizable al parsear DAGs sin AWS."""

import re


def normalize_spec(conf):
    allowed = {'batch_id', 'kind', 'source_batch_id'}
    if not isinstance(conf, dict) or set(conf) - allowed:
        raise ValueError('La configuración solo admite batch_id, kind y source_batch_id.')
    batch = conf.get('batch_id')
    kind = conf.get('kind', 'initial')
    source = conf.get('source_batch_id')
    if not isinstance(batch, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', batch):
        raise ValueError('Se requiere un batch_id estable de 1–64 caracteres seguros.')
    if kind not in ('initial', 'incremental', 'changes', 'reconcile'):
        raise ValueError('kind no válido.')
    if kind == 'incremental':
        if type(source) is not int or not 1 <= source <= 365:
            raise ValueError('El incremental requiere source_batch_id entero de 1 a 365.')
    elif source is not None:
        raise ValueError('Solo incremental admite source_batch_id.')
    return {'batch_id': batch, 'kind': kind, 'source_batch_id': source}
