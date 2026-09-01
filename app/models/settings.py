"""settings key-value table (bank account, bank due days ...)."""
from ..db import execute, query


def get_all():
    return {r["k"]: r["v"] for r in query("SELECT k, v FROM settings")}


def set_many(items):
    for k, v in items.items():
        execute("INSERT INTO settings (k, v) VALUES (%s,%s) ON DUPLICATE KEY UPDATE v = VALUES(v)", [k, v])
