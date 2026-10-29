"""Aplica el esquema original a RDS y crea las dos colecciones si faltan."""

import os
from pathlib import Path

from ecommerce_dw.sources.mysql_connection import connect_mysql
from ecommerce_dw.sources.documentdb_connection import connect_documentdb


def main():
    connection = connect_mysql()
    try:
        with connection.cursor() as cursor:
            schema = Path(__file__).parent / "mysql" / "schema.sql"
            for statement in schema.read_text(encoding="utf-8").split(";"):
                if statement.strip():
                    cursor.execute(statement)
        connection.commit()
    finally:
        connection.close()

    client = connect_documentdb()
    try:
        db = client[os.getenv("MONGO_DATABASE", "ecommerce")]
        for name in ("reviews", "navigation_events"):
            if name not in db.list_collection_names():
                db.create_collection(name)
    finally:
        client.close()
    print("MySQL tables and MongoDB collections are ready.")


if __name__ == "__main__":
    main()
