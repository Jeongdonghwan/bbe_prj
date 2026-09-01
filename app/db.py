"""pymysql connection pool + per-request connection helpers."""
import queue

import pymysql
from flask import current_app, g
from pymysql.cursors import DictCursor

_pool: "queue.LifoQueue[pymysql.Connection]" = queue.LifoQueue()


def _connect():
    cfg = current_app.config
    return pymysql.connect(
        host=cfg["DB_HOST"],
        port=cfg["DB_PORT"],
        user=cfg["DB_USER"],
        password=cfg["DB_PASSWORD"],
        database=cfg["DB_NAME"],
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=False,
    )


def _acquire():
    try:
        conn = _pool.get_nowait()
        conn.ping(reconnect=True)
        return conn
    except queue.Empty:
        return _connect()


def _release(conn):
    if _pool.qsize() < current_app.config["DB_POOL_SIZE"]:
        _pool.put(conn)
    else:
        conn.close()


def get_db():
    """Return the request-scoped connection (acquired lazily)."""
    if "db" not in g:
        g.db = _acquire()
    return g.db


def query(sql, params=None):
    with get_db().cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def query_one(sql, params=None):
    with get_db().cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def execute(sql, params=None):
    """Run a write statement; returns lastrowid. Commit happens at teardown."""
    with get_db().cursor() as cur:
        cur.execute(sql, params)
        return cur.lastrowid


def init_app(app):
    @app.teardown_appcontext
    def _teardown(exc):
        conn = g.pop("db", None)
        if conn is None:
            return
        try:
            if exc is None:
                conn.commit()
            else:
                conn.rollback()
        finally:
            _release(conn)
