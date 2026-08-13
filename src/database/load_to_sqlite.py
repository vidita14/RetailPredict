"""Load cleaned data into SQLite (PRD Phase 3).

Load order respects foreign keys: dimensions (customers, products) before the
transactions fact table.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.data.transform_data import build_customers, build_products
from src.database import db
from src.utils.logging import get_logger

logger = get_logger("database.load")


def load(df: pd.DataFrame, db_path: Path | str | None = None) -> dict[str, int]:
    """Build dimensions from the transaction table and populate the database.

    `df` must be transformed output (canonical columns + `revenue`).
    """
    if df.empty:
        raise ValueError(
            "Refusing to load an empty dataset — the cleaning stage removed every row. "
            "Check `data/processed/quality_report.json` for which filter dropped them."
        )

    db.initialize_database(db_path)

    customers = build_customers(df)
    products = build_products(df)

    # Dates as ISO strings so SQLite's strftime() works on them directly.
    for column in ("first_purchase_date", "last_purchase_date"):
        customers[column] = pd.to_datetime(customers[column]).dt.strftime("%Y-%m-%d %H:%M:%S")

    transactions = df.rename(columns={"invoice_date": "transaction_date"})[
        [
            "invoice_no",
            "customer_id",
            "product_id",
            "transaction_date",
            "quantity",
            "unit_price",
            "revenue",
            "country",
        ]
    ].copy()
    transactions["transaction_date"] = pd.to_datetime(
        transactions["transaction_date"]
    ).dt.strftime("%Y-%m-%d %H:%M:%S")
    # Pandas NA does not map to SQL NULL through to_sql for object columns.
    transactions["customer_id"] = transactions["customer_id"].astype(object).where(
        transactions["customer_id"].notna(), None
    )

    db.write_dataframe(customers, "customers", db_path=db_path)
    db.write_dataframe(products, "products", db_path=db_path)
    db.write_dataframe(transactions, "transactions", db_path=db_path)

    counts = db.get_table_counts(db_path)
    logger.info(
        "Loaded: %s customers, %s products, %s transactions",
        f"{counts.get('customers', 0):,}",
        f"{counts.get('products', 0):,}",
        f"{counts.get('transactions', 0):,}",
    )
    return counts


def verify(db_path: Path | str | None = None) -> dict[str, object]:
    """Post-load integrity checks — surfaced by the pipeline and asserted in tests."""
    orphan_products = db.run_query(
        """
        SELECT COUNT(*) AS n FROM transactions t
        LEFT JOIN products p ON t.product_id = p.product_id
        WHERE p.product_id IS NULL
        """,
        db_path=db_path,
    )["n"][0]

    orphan_customers = db.run_query(
        """
        SELECT COUNT(*) AS n FROM transactions t
        LEFT JOIN customers c ON t.customer_id = c.customer_id
        WHERE t.customer_id IS NOT NULL AND c.customer_id IS NULL
        """,
        db_path=db_path,
    )["n"][0]

    indexes = db.run_query(
        "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'",
        db_path=db_path,
    )["name"].tolist()

    return {
        "table_counts": db.get_table_counts(db_path),
        "orphan_product_rows": int(orphan_products),
        "orphan_customer_rows": int(orphan_customers),
        "indexes": indexes,
    }
