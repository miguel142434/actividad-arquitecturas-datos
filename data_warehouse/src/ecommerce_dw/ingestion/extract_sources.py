"""Selección de las seis entidades, sin modificar fuentes ni ejecutar cargas."""

import csv
import hashlib
import json
import os
from pathlib import Path

from bson.codec_options import CodecOptions
from pymysql.cursors import SSCursor

from ecommerce_dw.sources.append_batch import BASE_ID, ITEM_BASE_ID, LINES_PER_BATCH
from ecommerce_dw.sources.documentdb_connection import connect_documentdb
from ecommerce_dw.sources.mysql_connection import connect_mysql
from .raw_sources import BATCH_SIZE, MYSQL_CSV_COLUMNS, MONGO_CSV_COLUMNS, _csv_value, flatten_mongo

ENTITIES = {**{f"mysql/{name}": list(cols) for name, cols in MYSQL_CSV_COLUMNS.items()},
            **{f"documentdb/{name}": list(cols) for name, cols in MONGO_CSV_COLUMNS.items()}}
NULL = "\\N"


def csv_value(value):
    if value is None:
        return NULL
    value = _csv_value(value)
    if value == NULL:
        raise ValueError("Un valor coincide con el marcador CSV de nulos; no se exportó el lote.")
    return value


def digest_row(row):
    values = [csv_value(value) for value in row]
    return hashlib.sha256(json.dumps(values, ensure_ascii=False, default=str).encode()).hexdigest()


def write_csv(path, columns, rows):
    with Path(path).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(columns)
        count = 0
        for row in rows:
            writer.writerow([csv_value(value) for value in row])
            count += 1
    return count


def batch_ids(source_batch_id, items=False):
    base = ITEM_BASE_ID if items else BASE_ID
    return [base + source_batch_id * 10 + index for index in range(LINES_PER_BATCH)]


def fetch_rows(connection, sql, params=()):
    cursor = connection.cursor(SSCursor)
    try:
        cursor.execute(sql, params)
        while rows := cursor.fetchmany(BATCH_SIZE):
            yield from rows
    finally:
        cursor.close()


def extract_mysql(directory, source_batch_id, previous, changes_only=False):
    """Snapshot MySQL de lectura: dimensiones completas para comparar y hechos acotados."""
    source = connect_mysql()
    outputs, checkpoint = {}, {}
    try:
        with source.cursor() as cursor:
            cursor.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY")
        for table, columns in MYSQL_CSV_COLUMNS.items():
            entity = f"mysql/{table}"
            names = list(columns)
            sql = f"SELECT {', '.join(names)} FROM {table}"
            params = ()
            dimension = table in ("customers", "products")
            if source_batch_id is not None and not dimension:
                params = tuple(batch_ids(source_batch_id, table == "order_items"))
                sql += f" WHERE {names[0]} IN (%s, %s, %s)"
            sql += f" ORDER BY {names[0]}"
            rows = () if changes_only and not dimension else fetch_rows(source, sql, params)
            if dimension:
                signatures = {}
                old = previous.get(table, {})

                def changed_rows():
                    for row in rows:
                        key, signature = str(row[0]), digest_row(row)
                        signatures[key] = signature
                        if old.get(key) != signature:
                            yield row

                count = write_csv(Path(directory) / f"mysql_{table}.csv", names, changed_rows())
                if set(old) - set(signatures):
                    raise ValueError("Se eliminaron dimensiones; se requiere conciliación completa, no un delta.")
                checkpoint[table] = signatures
            else:
                count = write_csv(Path(directory) / f"mysql_{table}.csv", names, rows)
                if source_batch_id is not None and count != LINES_PER_BATCH:
                    raise ValueError(f"Lote de origen incompleto en {table}; no se publicó la extracción.")
            selection = {"strategy": "compare_content" if dimension else "full"}
            if changes_only and not dimension:
                selection = {"strategy": "empty"}
            elif params:
                selection = {"strategy": "keys", "column": names[0], "values": list(params)}
            outputs[entity] = {"file": f"mysql_{table}.csv", "rows": count, "columns": names,
                               "source_name": f"mysql.{table}", "selection": selection}
        source.rollback() # Cierra snapshot de solo lectura, no hay escrituras.
    finally:
        source.close()
    return outputs, checkpoint


def extract_documentdb(directory, source_batch_id, changes_only=False):
    if changes_only:
        return {f"documentdb/{name}": {
            "file": f"documentdb_{name}.csv", "columns": list(columns),
            "source_name": f"mongodb.{name}", "selection": {"strategy": "empty"},
            "rows": write_csv(Path(directory) / f"documentdb_{name}.csv", columns, ())
        } for name, columns in MONGO_CSV_COLUMNS.items()}
    client = connect_documentdb()
    outputs = {}
    try:
        database = client.get_database(os.getenv("MONGO_DATABASE", "ecommerce"),
                                       codec_options=CodecOptions(tz_aware=True))
        for collection, columns in MONGO_CSV_COLUMNS.items():
            query = {}
            if source_batch_id is not None:
                prefix = "review" if collection == "reviews" else "event"
                query = {"_id": {"$in": [f"{prefix}-{key:08d}" for key in batch_ids(source_batch_id)]}}
            cursor = database[collection].find(query).sort("_id", 1).batch_size(BATCH_SIZE)
            try:
                rows = (flatten_mongo(collection, document, None)[1][:-2] for document in cursor)
                filename = f"documentdb_{collection}.csv"
                count = write_csv(Path(directory) / filename, columns, rows)
            finally:
                cursor.close()
            if source_batch_id is not None and count != LINES_PER_BATCH:
                raise ValueError(f"Lote de origen incompleto en {collection}; no se publicó la extracción.")
            outputs[f"documentdb/{collection}"] = {
                "file": filename, "rows": count, "columns": list(columns),
                "source_name": f"mongodb.{collection}",
                "selection": {"strategy": "keys" if query else "full", "filter": query}}
    finally:
        client.close()
    return outputs
