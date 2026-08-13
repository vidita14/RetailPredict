"""Feature derivation on cleaned data (PRD Section 8.A).

Builds the revenue field and the customer/product dimension tables that
`load_to_sqlite.py` writes into the database.
"""

from __future__ import annotations

import pandas as pd

from src.utils.logging import get_logger

logger = get_logger("data.transform")


def add_revenue(df: pd.DataFrame) -> pd.DataFrame:
    """Attach the derived `revenue` field (Quantity x UnitPrice)."""
    out = df.copy()
    out["revenue"] = (out["quantity"] * out["unit_price"]).round(2)
    return out


def transform(df: pd.DataFrame) -> pd.DataFrame:
    """Apply all derived fields and return the transaction-level fact table."""
    out = add_revenue(df)
    out = out.sort_values("invoice_date").reset_index(drop=True)
    logger.info("Transformed %s transaction rows", f"{len(out):,}")
    return out


def build_products(df: pd.DataFrame) -> pd.DataFrame:
    """Product dimension: one row per product_id.

    A StockCode occasionally carries several spellings of its description across
    invoices; the most frequent spelling wins so the catalog stays deterministic.
    """
    name_counts = (
        df.groupby(["product_id", "description"], observed=True)
        .size()
        .reset_index(name="n")
        .sort_values(["product_id", "n"], ascending=[True, False])
    )
    products = (
        name_counts.drop_duplicates(subset="product_id", keep="first")
        .rename(columns={"description": "product_name"})[["product_id", "product_name"]]
        .copy()
    )
    # `category` is absent from UCI-style data; kept nullable for other datasets.
    products["category"] = None
    logger.info("Built product dimension: %s products", f"{len(products):,}")
    return products.reset_index(drop=True)


def build_customers(df: pd.DataFrame) -> pd.DataFrame:
    """Customer dimension with materialized totals (PRD Section 12).

    Guest rows (null customer_id) are excluded — they have no customer identity
    to aggregate against.
    """
    identified = df[df["customer_id"].notna()].copy()

    customers = (
        identified.groupby("customer_id", observed=True)
        .agg(
            first_purchase_date=("invoice_date", "min"),
            last_purchase_date=("invoice_date", "max"),
            total_orders=("invoice_no", "nunique"),
            total_spend=("revenue", "sum"),
        )
        .reset_index()
    )

    # A customer may order from more than one country; attribute them to the
    # country they ordered from most often.
    country_counts = (
        identified.groupby(["customer_id", "country"], observed=True)
        .size()
        .reset_index(name="n")
        .sort_values(["customer_id", "n"], ascending=[True, False])
        .drop_duplicates(subset="customer_id", keep="first")[["customer_id", "country"]]
    )

    customers = customers.merge(country_counts, on="customer_id", how="left")
    customers["total_spend"] = customers["total_spend"].round(2)

    logger.info("Built customer dimension: %s customers", f"{len(customers):,}")
    return customers[
        [
            "customer_id",
            "country",
            "first_purchase_date",
            "last_purchase_date",
            "total_orders",
            "total_spend",
        ]
    ]
