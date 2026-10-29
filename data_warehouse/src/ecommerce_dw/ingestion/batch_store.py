"""Publicación condicional por lote y confirmación separada del avance del pipeline."""

import hashlib
import csv
import io
import json
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from botocore.exceptions import ClientError

from .extract_sources import ENTITIES, extract_mysql, extract_documentdb

STATE_KEY = "control/state.json"


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def sha256(body):
    return hashlib.sha256(body).hexdigest()


def validate_id(batch_id):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", batch_id):
        raise ValueError("batch_id: usar 1–64 letras, números, guiones o guiones bajos.")


def manifest_key(batch_id):
    validate_id(batch_id)
    return f"control/batches/{batch_id}/manifest.json"


class BatchStore:
    def __init__(self, client, bucket):
        self.client, self.bucket = client, bucket

    def read(self, key):
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as error:
            if error.response["Error"]["Code"] in ("NoSuchKey", "404"):
                return None, None
            raise
        stream = response["Body"]
        try:
            return stream.read(), response["ETag"]
        finally:
            stream.close()

    def json(self, key):
        body, etag = self.read(key)
        return (json.loads(body) if body is not None else None), etag

    def put(self, key, body, **conditions):
        return self.client.put_object(Bucket=self.bucket, Key=key, Body=body,
                                      ServerSideEncryption="AES256", **conditions)

    def immutable(self, key, body):
        try:
            self.put(key, body, IfNoneMatch="*")
        except ClientError as error:
            if error.response["Error"]["Code"] != "PreconditionFailed":
                raise
            existing, _ = self.read(key)
            if existing != body:
                raise ValueError("El objeto del lote ya existe con otro contenido; no se sobrescribió.") from None

    def state(self):
        state, etag = self.json(STATE_KEY)
        return state or {"accepted": None, "pending": None, "source_batches": []}, etag

    def save_state(self, state, etag):
        condition = {"IfMatch": etag} if etag else {"IfNoneMatch": "*"}
        self.put(STATE_KEY, encode(state), **condition)

    def claim(self, batch_id, source_batch_id, kind):
        validate_id(batch_id)
        if kind not in ("initial", "incremental", "changes", "reconcile") or (kind == "incremental") != (source_batch_id is not None):
            raise ValueError("Selección de extracción inválida.")
        if source_batch_id is not None and (type(source_batch_id) is not int or not 1 <= source_batch_id <= 365):
            raise ValueError("source_batch_id debe estar entre 1 y 365.")
        existing, _ = self.json(manifest_key(batch_id))
        if existing:
            if existing["source_batch_id"] != source_batch_id or existing["kind"] != kind:
                raise ValueError("El batch_id ya identifica otra selección de origen.")
            return existing, True
        state, etag = self.state()
        pending = state["pending"]
        if pending:
            if pending["batch_id"] != batch_id or pending["source_batch_id"] != source_batch_id or pending["kind"] != kind:
                raise ValueError("Hay otro lote pendiente; recuperarlo y validarlo antes de avanzar.")
            return pending, False
        if (kind == "initial") != (state["accepted"] is None):
            raise ValueError("Primero se requiere una inicial; después solo lotes incrementales.")
        if source_batch_id is not None and source_batch_id in state["source_batches"]:
            raise ValueError("El lote de origen ya fue aceptado; reutilizar su batch_id de extracción.")
        request = {"batch_id": batch_id, "source_batch_id": source_batch_id, "kind": kind,
                   "parent": state["accepted"], "extracted_at": datetime.now(timezone.utc).isoformat()}
        state["pending"] = request
        self.save_state(state, etag)
        return request, False

    def checked_manifest(self, batch_id):
        manifest, _ = self.json(manifest_key(batch_id))
        if not manifest or manifest["batch_id"] != batch_id or set(manifest["entities"]) != set(ENTITIES):
            raise ValueError("No hay un manifiesto completo de las seis entidades.")
        return manifest

    def verify(self, manifest):
        validate_id(manifest["batch_id"])
        if set(manifest["entities"]) != set(ENTITIES):
            raise ValueError("No hay un manifiesto completo de las seis entidades.")
        for entity, entry in manifest["entities"].items():
            expected = f"raw/{entity}/batch_id={manifest['batch_id']}/data.csv"
            if entry["key"] != expected or entry["columns"] != ENTITIES[entity] or entry["file"] != entity.replace("/", "_") + ".csv":
                raise ValueError("Contrato/ruta de entidad no válido.")
            body, _ = self.read(expected)
            if body is None or sha256(body) != entry["sha256"]:
                raise ValueError("Archivo faltante o checksum incorrecto; no se puede reprocesar.")
            reader = csv.reader(io.StringIO(body.decode("utf-8")))
            if next(reader) != entry["columns"] or sum(1 for _ in reader) != entry["rows"]:
                raise ValueError("Cabecera o conteo CSV no coincide con el manifiesto.")
        key = f"control/batches/{manifest['batch_id']}/checkpoint.json"
        if manifest["checkpoint"]["key"] != key:
            raise ValueError("Ruta de checkpoint no válida.")
        body, _ = self.read(key)
        if body is None or sha256(body) != manifest["checkpoint"]["sha256"]:
            raise ValueError("Checkpoint faltante o corrupto.")
        return json.loads(body)

    def accept(self, batch_id):
        """Llamar únicamente tras carga, transformaciones y calidad exitosas (3.3–3.5)."""
        manifest = self.checked_manifest(batch_id)
        self.verify(manifest)
        state, etag = self.state()
        if state["accepted"] == batch_id:
            return
        if not state["pending"] or state["pending"]["batch_id"] != batch_id or manifest["parent"] != state["accepted"]:
            raise ValueError("El lote no es el siguiente pendiente de la cadena.")
        state["accepted"], state["pending"] = batch_id, None
        if manifest["source_batch_id"] is not None:
            state["source_batches"].append(manifest["source_batch_id"])
        self.save_state(state, etag)


def freeze_package(request, entities, checkpoint, temporary, package):
    """Congela un paquete conjunto; compartido por CLI y tareas separadas de Airflow."""
    batch_id = request['batch_id']
    manifest = {**request, "version": 1, "status": "EXTRACTED", "format": "csv-utf8-v1",
                "entities": entities, "completed_at": datetime.now(timezone.utc).isoformat(),
                "checkpoint": {"key": f"control/batches/{batch_id}/checkpoint.json"}}
    body = encode(checkpoint)
    (temporary / "checkpoint.json").write_bytes(body)
    manifest["checkpoint"]["sha256"] = sha256(body)
    for entity, entry in entities.items():
        entry["sha256"] = sha256((temporary / entry["file"]).read_bytes())
        entry["key"] = f"raw/{entity}/batch_id={batch_id}/data.csv"
    (temporary / "manifest.json").write_bytes(encode(manifest))
    temporary.rename(package) # Paquete congelado antes de subir datos.


def extract_batch(store, batch_id, source_batch_id, workspace, kind=None):
    kind = kind or ("initial" if source_batch_id is None else "incremental")
    request, published = store.claim(batch_id, source_batch_id, kind)
    if published:
        store.verify(request)
        return request # Repetición: nunca volver a consultar fuentes.
    root = Path(workspace)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    package = root / batch_id
    if not package.exists():
        previous = {}
        if request["parent"]:
            parent = store.checked_manifest(request["parent"])
            previous = store.verify(parent)
        if kind == 'reconcile':
            previous = {} # Foto completa para detectar también eliminaciones y correcciones históricas.
        temporary = Path(tempfile.mkdtemp(prefix=f".{batch_id}-", dir=root))
        try:
            entities, checkpoint = extract_mysql(temporary, source_batch_id, previous, changes_only=kind == "changes")
            entities.update(extract_documentdb(temporary, source_batch_id, changes_only=kind == "changes"))
            freeze_package(request, entities, checkpoint, temporary, package)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    manifest = json.loads((package / "manifest.json").read_bytes())
    if set(manifest["entities"]) != set(ENTITIES):
        raise ValueError("El paquete debe contener las seis entidades.")
    if any(manifest.get(key) != value for key, value in request.items()):
        raise ValueError("El paquete local no corresponde a la solicitud pendiente.")
    for entity, entry in manifest["entities"].items():
        if entry["file"] != entity.replace("/", "_") + ".csv":
            raise ValueError("Nombre local de archivo no válido.")
        body = (package / entry["file"]).read_bytes()
        if sha256(body) != entry["sha256"]:
            raise ValueError("El paquete local fue modificado; no se publicó.")
        store.immutable(entry["key"], body)
    body = (package / "checkpoint.json").read_bytes()
    if sha256(body) != manifest["checkpoint"]["sha256"]:
        raise ValueError("El checkpoint local fue modificado.")
    store.immutable(manifest["checkpoint"]["key"], body)
    # Publicar el manifiesto al final: un prefijo parcial no es un lote consumible.
    store.verify(manifest)
    store.immutable(manifest_key(batch_id), encode(manifest))
    return manifest


def replay_batch(store, batch_id, directory):
    manifest = store.checked_manifest(batch_id)
    store.verify(manifest)
    target = Path(directory) / batch_id
    target.mkdir(parents=True, exist_ok=True)
    for entry in manifest["entities"].values():
        body, _ = store.read(entry["key"])
        if body is None or sha256(body) != entry["sha256"]:
            raise ValueError("El objeto cambió durante la descarga.")
        path = target / entry["file"]
        if path.exists() and path.read_bytes() != body:
            raise ValueError("Ya existe un archivo local distinto; no se sobrescribió.")
        path.write_bytes(body)
    (target / "manifest.json").write_bytes(encode(manifest))
    return manifest
