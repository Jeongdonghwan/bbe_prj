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


def execute(sql, params=None, rowcount=False):
    """Run a write statement; returns lastrowid (or affected rows with rowcount=True). Commit at teardown."""
    with get_db().cursor() as cur:
        n = cur.execute(sql, params)
        return n if rowcount else cur.lastrowid


def commit():
    """지금까지의 쓰기를 확정한다.

    평소에는 teardown 이 알아서 커밋하므로 부를 일이 없다. **요청 밖(백그라운드 스레드)에서
    방금 만든 행을 읽어야 할 때만** 쓴다 — 스레드는 자기 커넥션을 쓰기 때문에 커밋 전에는
    그 행이 보이지 않는다.
    """
    conn = g.get("db")
    if conn is not None:
        conn.commit()


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
