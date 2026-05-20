"""SQL tool primitives over any SQLAlchemy-compatible engine.

Six primitives, all stateless except `connect` which registers an engine in a
process-local map keyed by `connection_id`.

Read-only enforcement is layered:
  1. Regex guard on every `execute_sql` / `validate_sql` — only
     SELECT/WITH/EXPLAIN/PRAGMA allowed.
  2. SQLite: `PRAGMA query_only = ON` at connection time. Engine-level
     enforcement; the connection physically cannot write.
  3. Warehouses (Snowflake/BigQuery/Databricks/MySQL/Postgres): connect as a
     role/user with SELECT grants only. The regex guard is defense in depth;
     the database is the authority.

Identifier quoting uses SQLAlchemy's `dialect.identifier_preparer.quote()`
so `describe_schema` and `sample_rows` work across `"name"` (SQLite, Postgres,
Snowflake) and `` `name` `` (MySQL, BigQuery, Databricks).
"""

from __future__ import annotations

import re
import time
import uuid
from typing import Any

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine

_connections: dict[str, Engine] = {}

_READ_ONLY_RE = re.compile(r"^\s*(SELECT|WITH|EXPLAIN|PRAGMA)\b", re.IGNORECASE)


def _is_read_only(sql: str) -> bool:
    return bool(_READ_ONLY_RE.match(sql.strip()))


def _get(connection_id: str) -> Engine:
    engine = _connections.get(connection_id)
    if engine is None:
        raise KeyError(f"Unknown connection_id: {connection_id}")
    return engine


def _quote(engine: Engine, name: str) -> str:
    """Quote an identifier the way the engine's dialect expects."""
    return engine.dialect.identifier_preparer.quote(name)


def connect(dsn: str) -> dict[str, Any]:
    """Open a database connection. Returns a `connection_id` for subsequent calls.

    For warehouses (Snowflake/BigQuery/Databricks) and Postgres/MySQL, connect
    via a read-only role at the DB level — this function does not attempt to
    enforce read-only beyond SQLite's pragma + the regex guard in `execute_sql`.
    """
    engine = create_engine(dsn, future=True)

    if engine.dialect.name == "sqlite":
        @event.listens_for(engine, "connect")
        def _enforce_readonly(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA query_only = ON")
            cur.close()

    conn_id = str(uuid.uuid4())
    _connections[conn_id] = engine
    return {"connection_id": conn_id, "dialect": engine.dialect.name}


def disconnect(connection_id: str) -> dict[str, Any]:
    engine = _connections.pop(connection_id, None)
    if engine is not None:
        engine.dispose()
    return {"success": True}


def list_tables(connection_id: str, pattern: str | None = None) -> dict[str, Any]:
    engine = _get(connection_id)
    tables = inspect(engine).get_table_names()
    if pattern:
        rx = re.compile(pattern)
        tables = [t for t in tables if rx.search(t)]
    return {"tables": tables}


def describe_schema(connection_id: str, tables: list[str]) -> dict[str, Any]:
    engine = _get(connection_id)
    insp = inspect(engine)
    out: dict[str, Any] = {}
    for t in tables:
        cols = [
            {"name": c["name"], "type": str(c["type"]), "nullable": c["nullable"]}
            for c in insp.get_columns(t)
        ]
        pk = insp.get_pk_constraint(t).get("constrained_columns", [])
        fks = [
            {
                "columns": fk["constrained_columns"],
                "ref_table": fk["referred_table"],
                "ref_columns": fk["referred_columns"],
            }
            for fk in insp.get_foreign_keys(t)
        ]
        try:
            with engine.connect() as conn:
                row_count = conn.execute(
                    text(f"SELECT COUNT(*) FROM {_quote(engine, t)}")
                ).scalar() or 0
        except Exception:
            row_count = None
        out[t] = {"columns": cols, "primary_keys": pk, "foreign_keys": fks, "row_count": row_count}
    return {"tables": out}


def sample_rows(connection_id: str, table: str, n: int = 5) -> dict[str, Any]:
    engine = _get(connection_id)
    with engine.connect() as conn:
        result = conn.execute(
            text(f"SELECT * FROM {_quote(engine, table)} LIMIT :n"), {"n": n}
        )
        cols = list(result.keys())
        rows = [dict(r._mapping) for r in result]
    return {"table": table, "columns": cols, "rows": rows}


def execute_sql(
    connection_id: str,
    sql: str,
    max_rows: int = 100,
    timeout_s: float = 30.0,
) -> dict[str, Any]:
    if not _is_read_only(sql):
        return {
            "success": False,
            "error": "Only read-only queries are permitted (SELECT/WITH/EXPLAIN/PRAGMA).",
        }

    engine = _get(connection_id)
    start = time.perf_counter()
    try:
        with engine.connect() as conn:
            result = conn.execute(text(sql))
            cols = list(result.keys()) if result.returns_rows else []
            rows: list[dict[str, Any]] = []
            if result.returns_rows:
                for i, r in enumerate(result):
                    if i >= max_rows:
                        break
                    rows.append(dict(r._mapping))
        return {
            "success": True,
            "columns": cols,
            "rows": rows,
            "row_count": len(rows),
            "truncated": result.returns_rows and len(rows) == max_rows,
            "elapsed_s": round(time.perf_counter() - start, 4),
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "elapsed_s": round(time.perf_counter() - start, 4),
        }


# Dialects that accept a plain `EXPLAIN <stmt>` as a dry-run.
_EXPLAIN_DIALECTS = {"postgresql", "mysql", "snowflake", "databricks"}


def validate_sql(connection_id: str, sql: str) -> dict[str, Any]:
    """Parse-only / EXPLAIN dry run. Cheap; use before `execute_sql`."""
    if not _is_read_only(sql):
        return {"valid": False, "error": "Only read-only queries are permitted."}

    engine = _get(connection_id)
    dialect = engine.dialect.name
    try:
        with engine.connect() as conn:
            if dialect == "sqlite":
                conn.execute(text(f"EXPLAIN QUERY PLAN {sql}"))
            elif dialect in _EXPLAIN_DIALECTS:
                conn.execute(text(f"EXPLAIN {sql}"))
            else:
                # BigQuery and any unknown dialect: dry-run by wrapping in a
                # zero-row outer select (LIMIT 0). Parses the inner SQL without
                # materializing rows.
                conn.execute(text(f"SELECT * FROM ({sql}) AS _v LIMIT 0"))
        return {"valid": True}
    except Exception as e:
        return {"valid": False, "error": str(e)}
