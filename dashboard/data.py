"""Cached data-fetch layer for the dashboard.

Pages call only these functions — never `src.database` or raw SQL directly.
Caching happens here so a page can be re-rendered on every widget interaction
without re-querying, and so tests can exercise the dashboard's data path without
Streamlit rendering (PRD Section 24).
"""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from src.analytics import (
    business_analytics,
    customer_analytics,
    insights,
    product_analytics,
)
from src.database import db
from src.recommendations import engine as recommendation_engine
from src.utils.config import DATABASE_PATH, EVALUATION_REPORT_PATH, QUALITY_REPORT_PATH

# Cached queries expire after 10 minutes so a mid-session pipeline re-run is
# eventually reflected without needing an app restart.
TTL = 600


def database_is_ready() -> tuple[bool, str]:
    """Check the database exists and has data, returning a user-facing message."""
    if not DATABASE_PATH.exists():
        return False, (
            f"No database found at `{DATABASE_PATH}`.\n\n"
            "Build it first:\n\n"
            "```\npython run_pipeline.py\n```"
        )
    try:
        counts = db.get_table_counts()
    except db.DatabaseError as exc:
        return False, f"Could not read the database: {exc}"

    if not counts.get("transactions"):
        return False, (
            "The database exists but contains no transactions. "
            "Re-run `python run_pipeline.py` and check the data-quality report."
        )
    return True, ""


# --- Business / home ---------------------------------------------------------

@st.cache_data(ttl=TTL)
def kpis() -> dict[str, float]:
    return business_analytics.get_kpis()


@st.cache_data(ttl=TTL)
def monthly_revenue() -> pd.DataFrame:
    return business_analytics.get_monthly_revenue()


@st.cache_data(ttl=TTL)
def segment_distribution() -> pd.DataFrame:
    return business_analytics.get_segment_distribution()


@st.cache_data(ttl=TTL)
def revenue_concentration() -> pd.DataFrame:
    return business_analytics.get_revenue_concentration()


@st.cache_data(ttl=TTL)
def underperforming_products(limit: int = 10, min_orders: int = 5) -> pd.DataFrame:
    return business_analytics.get_underperforming_products(limit, min_orders)


@st.cache_data(ttl=TTL)
def business_insights() -> list:
    return insights.generate()


# --- Customers ---------------------------------------------------------------

@st.cache_data(ttl=TTL)
def customer_ids() -> list[str]:
    return db.get_customer_ids()


@st.cache_data(ttl=TTL)
def customer_record(customer_id: str) -> pd.DataFrame:
    return db.get_customer(customer_id)


@st.cache_data(ttl=TTL)
def customer_purchases(customer_id: str) -> pd.DataFrame:
    return customer_analytics.get_customer_purchase_history(customer_id)


@st.cache_data(ttl=TTL)
def customer_monthly_spend(customer_id: str) -> pd.DataFrame:
    return customer_analytics.get_customer_monthly_spend(customer_id)


@st.cache_data(ttl=TTL)
def top_customers(limit: int = 10) -> pd.DataFrame:
    return customer_analytics.get_top_customers(limit)


@st.cache_data(ttl=TTL)
def customer_table() -> pd.DataFrame:
    """All customers with segment and RFM columns — the segmentation page grid."""
    return db.run_query(
        """
        SELECT customer_id, country, segment, rfm_score,
               r_score, f_score, m_score,
               recency_days, total_orders, total_spend, segment_reason
        FROM customers
        ORDER BY total_spend DESC
        """
    )


@st.cache_data(ttl=TTL)
def new_vs_returning() -> pd.DataFrame:
    return customer_analytics.get_new_vs_returning_by_month()


# --- Products ----------------------------------------------------------------

@st.cache_data(ttl=TTL)
def top_products(limit: int = 10, country: str | None = None) -> pd.DataFrame:
    return product_analytics.get_best_selling_products(limit, country)


@st.cache_data(ttl=TTL)
def product_performance() -> pd.DataFrame:
    return product_analytics.get_product_performance()


@st.cache_data(ttl=TTL)
def co_occurrence_pairs(min_co_occurrence: int = 5, limit: int = 50) -> pd.DataFrame:
    return product_analytics.get_co_occurrence_pairs(min_co_occurrence, limit)


@st.cache_data(ttl=TTL)
def countries() -> list[str]:
    result = db.run_query(
        "SELECT DISTINCT country FROM transactions WHERE country IS NOT NULL ORDER BY country"
    )
    return result["country"].tolist()


# --- Recommendations ---------------------------------------------------------

@st.cache_data(ttl=TTL)
def recommendations(customer_id: str) -> pd.DataFrame:
    """Precomputed recommendations, falling back to live generation.

    The pipeline materializes these, but a customer added since the last run
    still gets an answer rather than an empty panel.
    """
    stored = recommendation_engine.load_recommendations(customer_id)
    if not stored.empty:
        return stored

    live = recommendation_engine.recommend(customer_id)
    if not live:
        return pd.DataFrame(
            columns=["rank", "product_id", "product_name", "score",
                     "source_method", "reason_text"]
        )
    return pd.DataFrame(
        [
            {"rank": i, "product_id": r.product_id, "product_name": r.product_name,
             "score": r.score, "source_method": r.source_method,
             "reason_text": r.reason_text}
            for i, r in enumerate(live, start=1)
        ]
    )


@st.cache_data(ttl=TTL)
def association_rules(limit: int = 50) -> pd.DataFrame:
    return db.run_query(
        """
        SELECT pa.product_name AS antecedent_name, pc.product_name AS consequent_name,
               r.antecedent, r.consequent, r.support, r.confidence, r.lift
        FROM association_rules r
        LEFT JOIN products pa ON r.antecedent = pa.product_id
        LEFT JOIN products pc ON r.consequent = pc.product_id
        ORDER BY r.lift DESC
        LIMIT ?
        """,
        (limit,),
    )


@st.cache_data(ttl=TTL)
def recommendation_method_mix() -> pd.DataFrame:
    return db.run_query(
        """
        SELECT source_method, COUNT(*) AS recommendations
        FROM recommendations
        GROUP BY source_method
        ORDER BY recommendations DESC
        """
    )


# --- Pipeline artifacts ------------------------------------------------------

@st.cache_data(ttl=TTL)
def quality_report() -> dict | None:
    if not QUALITY_REPORT_PATH.exists():
        return None
    return json.loads(QUALITY_REPORT_PATH.read_text(encoding="utf-8"))


@st.cache_data(ttl=TTL)
def evaluation_report() -> dict | None:
    if not EVALUATION_REPORT_PATH.exists():
        return None
    return json.loads(EVALUATION_REPORT_PATH.read_text(encoding="utf-8"))
