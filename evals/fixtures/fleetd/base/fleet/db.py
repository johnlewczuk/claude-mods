"""SQLite access helpers. Every module goes through these."""
import os
import sqlite3
from contextlib import contextmanager


def connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def query(conn, sql, params=()):
    """Run a SELECT and return all rows as dicts."""
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def query_one(conn, sql, params=()):
    """Run a SELECT and return the first row as a dict, or None."""
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None


@contextmanager
def transaction(conn):
    """Commit on success, roll back on any exception."""
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def migrate(conn, migrations_dir):
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    current = query_one(conn, "SELECT MAX(version) AS v FROM schema_version")["v"] or 0
    for name in sorted(os.listdir(migrations_dir)):
        version = int(name.split("_", 1)[0])
        if version > current:
            with open(os.path.join(migrations_dir, name)) as f:
                conn.executescript(f.read())
            conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
            conn.commit()
