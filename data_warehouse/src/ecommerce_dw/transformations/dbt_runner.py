"""Runner adaptado de DE-DW: ejecutable propio y Redshift en lugar de lock DuckDB."""

import os
from pathlib import Path
import subprocess

DBT_PROJECT = Path(__file__).resolve().parents[2] / 'dbt'


def run_dbt(command, selector=None):
    if command not in ('deps', 'seed', 'run', 'snapshot', 'test', 'parse'):
        raise ValueError('Comando dbt no permitido por este runner.')
    executable = os.getenv('DBT_EXECUTABLE', str(DBT_PROJECT.parents[1] / '.venv/bin/dbt'))
    arguments = [executable, command, '--project-dir', str(DBT_PROJECT), '--profiles-dir', str(DBT_PROJECT)]
    if selector is not None:
        arguments.extend(['--select', selector])
    if command not in ('deps', 'parse'):
        arguments.extend(['--threads', '1'])
    subprocess.run(arguments, check=True)
