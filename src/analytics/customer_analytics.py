"""Customer-level SQL analytics (PRD Section 13).

Every function returns a DataFrame and contains no formatting or charting logic.
Guest transactions (customer_id IS NULL) are excluded throughout — they cannot
be attributed to a customer.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.database import db


def get_customer_summary(db_path: Path | str | None = None) -> pd.DataFrame:
    """Revenue, order count, and purchase dates per customer.

    Feeds the RFM Monetary/Frequency inputs and the dashboard customer table.
    """
    return db.run_query(
        """
        SELECT customer_id,
               SUM(revenue)                AS total_spend,
               COUNT(DISTINCT invoice_no)  AS total_orders,
               SUM(quantity)               AS total_units,
               MIN(transaction_date)       AS first_purchase_date,
               MAX(transaction_date)       AS last_purchase_date,
               SUM(revenue) / COUNT(DISTINCT invoice_no) AS avg_order_value
        FROM transactions
        WHERE customer_id IS NOT NULL
        GROUP BY customer_id
        ORDER BY total_spend DESC
        """,
        db_path=db_path,
    )


def get_top_customers(limit: int = 10, db_path: Path | str | None = None) -> pd.DataFrame:
    """Highest-spending customers, with segment attached when available."""
    return db.run_query(
        """
        SELECT c.customer_id, c.country, c.segment,
               c.total_spend, c.total_orders,
               c.total_spend / NULLIF(c.total_orders, 0) AS avg_order_value,
               c.last_purchase_date
        FROM customers c
        ORDER BY c.total_spend DESC
        LIMIT ?
        """,
        (limit,),
        db_path,
    )


def get_new_vs_returning_by_month(db_path: Path | str | None = None) -> pd.DataFrame:
    """Monthly count of new vs. returning customers (PRD Section 13).

    A customer counts as "New" in the month containing their first purchase and
    "Returning" in every later month they transact in.
    """
    return db.run_query(
        """
        SELECT month, customer_type, COUNT(DISTINCT customer_id) AS customers
        FROM (
            SELECT strftime('%Y-%m', t.transaction_date) AS month,
                   t.customer_id,
                   CASE
                       WHEN strftime('%Y-%m', t.transaction_date)
                            = strftime('%Y-%m', c.first_purchase_date)
                       THEN 'New' ELSE 'Returning'
                   END AS customer_type
            FROM transactions t
            JOIN customers c ON t.customer_id = c.customer_id
            WHERE t.customer_id IS NOT NULL
        )
        GROUP BY month, customer_type
        ORDER BY month, customer_type
        """,
        db_path=db_path,
    )


def get_customer_country_distribution(db_path: Path | str | None = None) -> pd.DataFrame:
    """Customer count and revenue by country."""
    return db.run_query(
        """
        SELECT country,
               COUNT(*)         AS customers,
               SUM(total_spend) AS revenue,
               SUM(total_orders) AS orders
        FROM customers
        GROUP BY country
        ORDER BY revenue DESC
        """,
        db_path=db_path,
    )


def get_customer_purchase_history(
    customer_id: str, db_path: Path | str | None = None
) -> pd.DataFrame:
    """One customer's line-item history, most recent first."""
    return db.get_customer_purchases(customer_id, db_path)


def get_customer_monthly_spend(
    customer_id: str, db_path: Path | str | None = None
) -> pd.DataFrame:
    """A single customer's spend over time — drives the profile sparkline."""
    return db.run_query(
        """
        SELECT strftime('%Y-%m', transaction_date) AS month,
               SUM(revenue) AS revenue,
               COUNT(DISTINCT invoice_no) AS orders
        FROM transactions
        WHERE customer_id = ?
        GROUP BY month
        ORDER BY month
        """,
        (str(customer_id),),
        db_path,
    )
