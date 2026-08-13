"""The single data-access boundary (PRD Section 22).

No other module in the project opens a SQLite connection. Everything —
pipeline stages, analytics, dashboard pages — goes through the helpers here,
so connection handling, foreign-key enforcement, and error surfacing live in
exactly one place.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

import pandas as pd

from src.utils.config import DATABASE_PATH, SCHEMA_PATH
from src.utils.logging import get_logger

logger = get_logger("database.db")


class DatabaseError(Exception):
    """Raised for connection/query failures, with an actionable message."""


@contextmanager
def get_connection(
    db_path: Path | str | None = None, *, read_only: bool = False
) -> Iterator[sqlite3.Connection]:
    """Yield a SQLite connection with foreign keys enforced.

    SQLite disables foreign-key checks by default and re-enables them *per
    connection*, so the PRAGMA has to be issued here on every connect or the
    schema's REFERENCES clauses are decorative.
    """
    path = Path(db_path) if db_path else DATABASE_PATH

    if read_only and not path.exists() and str(path) != ":memory:":
        raise DatabaseError(
            f"Database not found at {path}.\n"
            "Run `python run_pipeline.py` to build it from your raw CSV."
        )

    connection: sqlite3.Connection | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(path))
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        yield connection
        connection.commit()
    except sqlite3.Error as exc:
        if connection is not None:
            connection.rollback()
        raise DatabaseError(f"Database operation failed against {path}: {exc}") from exc
    finally:
        if connection is not None:
            connection.close()


def initialize_database(db_path: Path | str | None = None) -> None:
    """(Re)create the schema from `schema.sql`, dropping any existing tables."""
    schema_sql = Path(SCHEMA_PATH).read_text(encoding="utf-8")
    with get_connection(db_path) as conn:
        conn.executescript(schema_sql)
    logger.info("Initialized schema at %s", db_path or DATABASE_PATH)


def run_query(
    sql: str, params: Sequence[Any] | dict[str, Any] | None = None,
    db_path: Path | str | None = None,
) -> pd.DataFrame:
    """Execute a SELECT and return the result as a DataFrame."""
    with get_connection(db_path, read_only=True) as conn:
        return pd.read_sql_query(sql, conn, params=params)


def execute(
    sql: str, params: Sequence[Any] | dict[str, Any] | None = None,
    db_path: Path | str | None = None,
) -> int:
    """Execute a single write statement; returns affected row count."""
    with get_connection(db_path) as conn:
        cursor = conn.execute(sql, params or ())
        return cursor.rowcount


def write_dataframe(
    df: pd.DataFrame, table: str, *, if_exists: str = "append",
    db_path: Path | str | None = None,
) -> int:
    """Bulk-insert a DataFrame into `table`. Returns rows written."""
    if df.empty:
        logger.warning("Skipped writing to '%s': DataFrame is empty", table)
        return 0
    with get_connection(db_path) as conn:
        df.to_sql(table, conn, if_exists=if_exists, index=False)
    logger.info("Wrote %s rows into '%s'", f"{len(df):,}", table)
    return len(df)


def table_exists(table: str, db_path: Path | str | None = None) -> bool:
    result = run_query(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
        (table,),
        db_path,
    )
    return not result.empty


def get_table_counts(db_path: Path | str | None = None) -> dict[str, int]:
    """Row count per table — used by pipeline verification and tests."""
    tables = run_query(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'",
        db_path=db_path,
    )
    counts: dict[str, int] = {}
    for name in tables["name"]:
        counts[name] = int(run_query(f"SELECT COUNT(*) AS n FROM {name}", db_path=db_path)["n"][0])
    return counts


# --- Convenience accessors used by the dashboard -----------------------------

def get_customer(customer_id: str, db_path: Path | str | None = None) -> pd.DataFrame:
    """Full customer record including RFM/segment columns. Empty if not found."""
    return run_query("SELECT * FROM customers WHERE customer_id = ?", (str(customer_id),), db_path)


def get_customer_ids(db_path: Path | str | None = None) -> list[str]:
    """All customer IDs, highest spend first (drives dashboard select boxes)."""
    result = run_query(
        "SELECT customer_id FROM customers ORDER BY total_spend DESC", db_path=db_path
    )
    return result["customer_id"].astype(str).tolist()


def get_customer_purchases(
    customer_id: str, db_path: Path | str | None = None
) -> pd.DataFrame:
    """A customer's purchase history, most recent first."""
    return run_query(
        """
        SELECT t.invoice_no, t.transaction_date, t.product_id, p.product_name,
               t.quantity, t.unit_price, t.revenue
        FROM transactions t
        LEFT JOIN products p ON t.product_id = p.product_id
        WHERE t.customer_id = ?
        ORDER BY t.transaction_date DESC
        """,
        (str(customer_id),),
        db_path,
    )
