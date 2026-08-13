"""Business-level KPIs, trends, and the inputs for auto-generated insights
(PRD Sections 13 and 17).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.database import db


def get_kpis(db_path: Path | str | None = None) -> dict[str, float]:
    """Headline metrics for the dashboard Home page.

    `repeat_rate` counts identified customers with more than one distinct
    invoice, as a share of all identified customers.
    """
    totals = db.run_query(
        """
        SELECT COALESCE(SUM(revenue), 0)          AS total_revenue,
               COUNT(DISTINCT invoice_no)         AS total_orders,
               COUNT(DISTINCT customer_id)        AS total_customers,
               COALESCE(SUM(quantity), 0)         AS total_units,
               COUNT(*)                           AS total_line_items
        FROM transactions
        """,
        db_path=db_path,
    ).iloc[0]

    repeat = db.run_query(
        """
        SELECT
            COUNT(*) AS identified_customers,
            SUM(CASE WHEN order_count > 1 THEN 1 ELSE 0 END) AS repeat_customers
        FROM (
            SELECT customer_id, COUNT(DISTINCT invoice_no) AS order_count
            FROM transactions
            WHERE customer_id IS NOT NULL
            GROUP BY customer_id
        )
        """,
        db_path=db_path,
    ).iloc[0]

    guest = db.run_query(
        """
        SELECT COALESCE(SUM(revenue), 0) AS guest_revenue, COUNT(*) AS guest_rows
        FROM transactions WHERE customer_id IS NULL
        """,
        db_path=db_path,
    ).iloc[0]

    total_orders = int(totals["total_orders"]) or 1
    identified = int(repeat["identified_customers"]) or 1

    return {
        "total_revenue": float(totals["total_revenue"]),
        "total_orders": int(totals["total_orders"]),
        "total_customers": int(totals["total_customers"]),
        "total_units": int(totals["total_units"]),
        "total_line_items": int(totals["total_line_items"]),
        "avg_order_value": float(totals["total_revenue"]) / total_orders,
        "repeat_rate": float(repeat["repeat_customers"] or 0) / identified,
        "guest_revenue": float(guest["guest_revenue"]),
        "guest_rows": int(guest["guest_rows"]),
    }


def get_monthly_revenue(db_path: Path | str | None = None) -> pd.DataFrame:
    """Revenue, orders, and customers per month."""
    return db.run_query(
        """
        SELECT strftime('%Y-%m', transaction_date)  AS month,
               SUM(revenue)                         AS revenue,
               COUNT(DISTINCT invoice_no)           AS orders,
               COUNT(DISTINCT customer_id)          AS customers
        FROM transactions
        GROUP BY month
        ORDER BY month
        """,
        db_path=db_path,
    )


def get_segment_distribution(db_path: Path | str | None = None) -> pd.DataFrame:
    """Customer count and revenue contribution per RFM segment."""
    return db.run_query(
        """
        SELECT COALESCE(segment, 'Unsegmented') AS segment,
               COUNT(*)                          AS customers,
               SUM(total_spend)                  AS revenue,
               AVG(total_spend)                  AS avg_spend,
               AVG(recency_days)                 AS avg_recency_days,
               AVG(total_orders)                 AS avg_orders
        FROM customers
        GROUP BY segment
        ORDER BY revenue DESC
        """,
        db_path=db_path,
    )


def get_revenue_concentration(db_path: Path | str | None = None) -> pd.DataFrame:
    """Cumulative revenue share by customer, ranked highest-spend first.

    The basis for the Pareto insight; the cumulative share is computed with a
    window function rather than in Pandas so SQL does the aggregation work.
    """
    return db.run_query(
        """
        SELECT customer_id, total_spend,
               SUM(total_spend) OVER (
                   ORDER BY total_spend DESC
                   ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
               ) / SUM(total_spend) OVER () AS cumulative_revenue_share,
               ROW_NUMBER() OVER (ORDER BY total_spend DESC) * 1.0
                   / COUNT(*) OVER () AS cumulative_customer_share
        FROM customers
        WHERE total_spend > 0
        ORDER BY total_spend DESC
        """,
        db_path=db_path,
    )


def get_underperforming_products(
    limit: int = 10, min_orders: int = 5, db_path: Path | str | None = None
) -> pd.DataFrame:
    """Lowest-revenue products that still have enough orders to be meaningful.

    The `min_orders` floor prevents one-off items from dominating the list
    (PRD Section 17).
    """
    return db.run_query(
        """
        SELECT p.product_id, p.product_name,
               SUM(t.revenue)               AS total_revenue,
               SUM(t.quantity)              AS units_sold,
               COUNT(DISTINCT t.invoice_no) AS orders
        FROM products p
        JOIN transactions t ON p.product_id = t.product_id
        GROUP BY p.product_id, p.product_name
        HAVING orders >= ?
        ORDER BY total_revenue ASC
        LIMIT ?
        """,
        (min_orders, limit),
        db_path,
    )


def get_dataset_date_range(db_path: Path | str | None = None) -> dict[str, str]:
    """First and last transaction date — the reference point for RFM recency."""
    row = db.run_query(
        "SELECT MIN(transaction_date) AS start_date, MAX(transaction_date) AS end_date "
        "FROM transactions",
        db_path=db_path,
    ).iloc[0]
    return {"start_date": row["start_date"], "end_date": row["end_date"]}
