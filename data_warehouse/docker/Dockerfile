FROM apache/airflow:2.11.2-python3.11

# Se conserva la imagen y el aislamiento de dbt de DE-DW. Las restricciones
# Airflow fijan boto3=1.42.61; el extractor requiere 1.43.116 para sus APIs S3.
# No instalar esas dependencias encima del entorno de Airflow.
COPY --chown=airflow:root requirements-sources.txt requirements-ingestion.txt requirements-warehouse.txt /tmp/requirements/
RUN python -m pip check \
    && python -m venv /home/airflow/dbt-venv \
    && /home/airflow/dbt-venv/bin/pip install --no-cache-dir -r /tmp/requirements/requirements-warehouse.txt \
    && /home/airflow/dbt-venv/bin/pip check \
    && ln -s /home/airflow/dbt-venv/bin/dbt /home/airflow/.local/bin/dbt
