"""Columnas y aplanamiento seleccionados de DE-DW; sin DDL ni carga DuckDB."""

from datetime import datetime

from bson import json_util

BATCH_SIZE = 1000

def flatten_mongo(collection, document, loaded_at):
    if collection == "reviews":
        customer = document.get("customer") or {}
        product = document.get("product") or {}
        values = (
            document.get("review_id"), customer.get("customer_id"),
            product.get("product_id"), document.get("rating"),
            document.get("reviewed_at"), json_util.dumps(document), loaded_at,
            "mongodb.reviews",
        )
        return "raw.mongo_reviews", values

    customer = document.get("customer") or {}
    product = document.get("product") or {}
    device = document.get("device") or {}
    values = (
        document.get("event_id"), document.get("event_type"), document.get("occurred_at"),
        customer.get("customer_id"), product.get("product_id"),
        device.get("sales_channel"), json_util.dumps(document), loaded_at,
        "mongodb.navigation_events",
    )
    return "raw.mongo_navigation_events", values

MYSQL_CSV_COLUMNS = {
    "customers": {"customer_id": "BIGINT", "name": "VARCHAR", "email": "VARCHAR", "phone": "VARCHAR", "city": "VARCHAR", "department": "VARCHAR", "registration_date": "DATE", "updated_at": "TIMESTAMP"},
    "products": {"product_id": "BIGINT", "name": "VARCHAR", "category": "VARCHAR", "price": "DECIMAL(12,2)", "description": "VARCHAR", "is_active": "BOOLEAN", "updated_at": "TIMESTAMP"},
    "orders": {"order_id": "BIGINT", "customer_id": "BIGINT", "order_date": "TIMESTAMP", "status": "VARCHAR", "sales_channel": "VARCHAR", "payment_method": "VARCHAR", "total": "DECIMAL(14,2)"},
    "order_items": {"order_item_id": "BIGINT", "order_id": "BIGINT", "product_id": "BIGINT", "quantity": "INTEGER", "unit_price": "DECIMAL(12,2)", "subtotal": "DECIMAL(14,2)"},
}

MONGO_CSV_COLUMNS = {
    "reviews": {"review_id": "BIGINT", "customer_id": "BIGINT", "product_id": "BIGINT", "rating": "INTEGER", "reviewed_at": "TIMESTAMPTZ", "document_json": "VARCHAR"},
    "navigation_events": {"event_id": "BIGINT", "event_type": "VARCHAR", "occurred_at": "TIMESTAMPTZ", "customer_id": "BIGINT", "product_id": "BIGINT", "sales_channel": "VARCHAR", "document_json": "VARCHAR"},
}

def _csv_value(value):
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
