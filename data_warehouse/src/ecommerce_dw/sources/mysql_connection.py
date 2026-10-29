"""Conexión explícita a MySQL con CA e identidad verificadas; sin valores secretos en logs."""

import os
import ssl

import pymysql


def connect_mysql():
    required = ("MYSQL_HOST", "MYSQL_DATABASE", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_SSL_CA")
    missing = [name for name in required if not os.environ.get(name, "").strip()]
    if missing:
        raise ValueError("Faltan variables: " + ", ".join(missing))
    try:
        port = int(os.environ.get("MYSQL_PORT", "3306"))
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        raise ValueError("MYSQL_PORT debe ser un entero entre 1 y 65535.") from None
    try:
        context = ssl.create_default_context(cafile=os.environ["MYSQL_SSL_CA"])
    except (OSError, ssl.SSLError):
        raise ValueError("MYSQL_SSL_CA debe apuntar a un archivo PEM de CA válido y legible.") from None
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    connection = pymysql.connect(
        host=os.environ["MYSQL_HOST"],
        port=port,
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        database=os.environ["MYSQL_DATABASE"],
        charset="utf8mb4",
        autocommit=False,
        ssl=context,
        connect_timeout=10,
        read_timeout=30,
        write_timeout=30,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute("SHOW SESSION STATUS LIKE 'Ssl_cipher'")
            cipher = cursor.fetchone()
            if not cipher or not cipher[1]:
                raise ValueError("MySQL no negoció TLS; conexión cerrada sin aplicar esquema ni datos.")
        return connection
    except Exception:
        connection.close()
        raise
