"""Conexión a DocumentDB conservando MONGODB_URI y la base del proyecto original."""

import os

from pymongo import MongoClient


def connect_documentdb():
    for variable in ("MONGODB_URI", "MONGO_TLS_CA_FILE"):
        if not os.environ.get(variable, "").strip():
            raise ValueError(f"Falta la variable {variable}.")
    return MongoClient(
        os.environ["MONGODB_URI"],
        tls=True,
        tlsCAFile=os.environ["MONGO_TLS_CA_FILE"],
        tlsAllowInvalidCertificates=False,
        tlsAllowInvalidHostnames=False,
        replicaSet="rs0",
        readPreference="primary",
        retryWrites=False,
        serverSelectionTimeoutMS=30000,
        connectTimeoutMS=10000,
    )
