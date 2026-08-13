"""Product-level SQL analytics, including the cross-sell co-occurrence base
that feeds market basket analysis (PRD Section 13).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.database import db


def get_best_selling_products(
    limit: int = 10, country: str | None = None, db_path: Path | str | None = None
) -> pd.DataFrame:
    """Top products by revenue, optionally filtered to one country."""
    where = "WHERE t.country = ?" if country else ""
    params: tuple = (country, limit) if country else (limit,)
    return db.run_query(
        f"""
        SELECT p.product_id, p.product_name,
               SUM(t.quantity)             AS units_sold,
               SUM(t.revenue)              AS total_revenue,
               COUNT(DISTINCT t.invoice_no) AS orders
        FROM transactions t
        JOIN products p ON t.product_id = p.product_id
        {where}
        GROUP BY p.product_id, p.product_name
        ORDER BY total_revenue DESC
        LIMIT ?
        """,
        params,
        db_path,
    )


def get_product_performance(db_path: Path | str | None = None) -> pd.DataFrame:
    """Full product catalog with sales metrics — the base for most product views."""
    return db.run_query(
        """
        SELECT p.product_id, p.product_name,
               COALESCE(SUM(t.quantity), 0)              AS units_sold,
               COALESCE(SUM(t.revenue), 0)               AS total_revenue,
               COUNT(DISTINCT t.invoice_no)              AS orders,
               COUNT(DISTINCT t.customer_id)             AS customers,
               COALESCE(AVG(t.unit_price), 0)            AS avg_unit_price
        FROM products p
        LEFT JOIN transactions t ON p.product_id = t.product_id
        GROUP BY p.product_id, p.product_name
        ORDER BY total_revenue DESC
        """,
        db_path=db_path,
    )


def get_co_occurrence_pairs(
    min_co_occurrence: int = 5, limit: int = 100, db_path: Path | str | None = None
) -> pd.DataFrame:
    """Products frequently bought together within the same invoice.

    The `a.product_id < b.product_id` predicate both removes self-pairs and
    deduplicates (A,B)/(B,A) into a single row.
    """
    return db.run_query(
        """
        SELECT a.product_id AS product_a, pa.product_name AS product_a_name,
               b.product_id AS product_b, pb.product_name AS product_b_name,
               COUNT(*) AS co_occurrence
        FROM transactions a
        JOIN transactions b
          ON a.invoice_no = b.invoice_no AND a.product_id < b.product_id
        JOIN products pa ON a.product_id = pa.product_id
        JOIN products pb ON b.product_id = pb.product_id
        GROUP BY a.product_id, b.product_id
        HAVING co_occurrence >= ?
        ORDER BY co_occurrence DESC
        LIMIT ?
        """,
        (min_co_occurrence, limit),
        db_path,
    )


def get_top_products_by_segment(
    segment: str, limit: int = 10, db_path: Path | str | None = None
) -> pd.DataFrame:
    """Best sellers within one RFM segment — the popularity fallback source."""
    return db.run_query(
        """
        SELECT p.product_id, p.product_name,
               SUM(t.revenue)  AS total_revenue,
               SUM(t.quantity) AS units_sold
        FROM transactions t
        JOIN customers c ON t.customer_id = c.customer_id
        JOIN products  p ON t.product_id  = p.product_id
        WHERE c.segment = ?
        GROUP BY p.product_id, p.product_name
        ORDER BY total_revenue DESC
        LIMIT ?
        """,
        (segment, limit),
        db_path,
    )


def get_top_products_by_country(
    country: str, limit: int = 10, db_path: Path | str | None = None
) -> pd.DataFrame:
    """Best sellers within one country — secondary popularity fallback."""
    return db.run_query(
        """
        SELECT p.product_id, p.product_name,
               SUM(t.revenue)  AS total_revenue,
               SUM(t.quantity) AS units_sold
        FROM transactions t
        JOIN products p ON t.product_id = p.product_id
        WHERE t.country = ?
        GROUP BY p.product_id, p.product_name
        ORDER BY total_revenue DESC
        LIMIT ?
        """,
        (country, limit),
        db_path,
    )


def get_global_top_products(
    limit: int = 10, db_path: Path | str | None = None
) -> pd.DataFrame:
    """Overall best sellers — the last-resort fallback when no segment or
    country context is available."""
    return get_best_selling_products(limit=limit, db_path=db_path)


def get_product_monthly_sales(
    product_id: str, db_path: Path | str | None = None
) -> pd.DataFrame:
    """One product's sales trend over time."""
    return db.run_query(
        """
        SELECT strftime('%Y-%m', transaction_date) AS month,
               SUM(quantity) AS units_sold,
               SUM(revenue)  AS revenue
        FROM transactions
        WHERE product_id = ?
        GROUP BY month
        ORDER BY month
        """,
        (str(product_id),),
        db_path,
    )
