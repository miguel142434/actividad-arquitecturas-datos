#!/usr/bin/env python3
"""Completa solo claves locales de Airflow ausentes, sin mostrar ni rotar secretos."""

import base64
import os
from pathlib import Path
import re
import secrets


def prepare(path):
    text = path.read_text()
    factories = {
        'POSTGRES_USER': lambda: 'airflow',
        'POSTGRES_PASSWORD': lambda: secrets.token_hex(24),
        'AIRFLOW_FERNET_KEY': lambda: base64.urlsafe_b64encode(os.urandom(32)).decode(),
        'AIRFLOW_SECRET_KEY': lambda: secrets.token_hex(32),
        'AIRFLOW_ADMIN_USERNAME': lambda: 'airflow',
        'AIRFLOW_ADMIN_PASSWORD': lambda: secrets.token_hex(24),
        'AIRFLOW_UID': lambda: str(os.getuid()),
    }
    for key, factory in factories.items():
        pattern = re.compile(rf'^{key}=(.*)$', re.MULTILINE)
        match = pattern.search(text)
        if match and match[1].strip(" '\""):
            continue
        replacement = f'{key}={factory()}'
        text = pattern.sub(lambda _: replacement, text) if match else text.rstrip()+'\n'+replacement+'\n'
    path.write_text(text)
    path.chmod(0o600)


if __name__ == '__main__':
    prepare(Path(__file__).resolve().parents[1]/'.env')
    print('Configuración Airflow preparada; valores existentes conservados y secretos no mostrados.')
