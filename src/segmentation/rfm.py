"""Rule-based RFM segmentation (PRD Section 14).

Deterministic and fully explainable: quintile scores for Recency, Frequency,
and Monetary drive a fixed rule table, and every customer carries the reason
their segment was assigned.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.analytics import customer_analytics
from src.database import db
from src.utils.config import get_section
from src.utils.logging import get_logger

logger = get_logger("segmentation.rfm")

# Segment -> human-readable explanation template (PRD Section 16 explainability).
SEGMENT_REASONS = {
    "Champions": "Bought recently, buys often, and spends the most",
    "Loyal Customers": "Buys regularly and spends above average",
    "Potential Loyalists": "Recent customer with promising spend — worth nurturing",
    "New Customers": "Bought very recently but has not yet come back",
    "At-Risk": "Used to buy often and spend well, but has not purchased in a while",
    "Lost": "Has not purchased in a long time and had low frequency and spend",
    "Others": "Sits between the defined segments on recency, frequency, and spend",
}


def compute_rfm(
    df: pd.DataFrame, snapshot_date: pd.Timestamp | None = None, quantiles: int = 5
) -> pd.DataFrame:
    """Compute R/F/M values and quintile scores.

    `df` needs `customer_id`, `last_purchase_date`, `total_orders`, `total_spend`.
    Recency is measured against `snapshot_date`, defaulting to the day after the
    dataset's last transaction so the most recent customer scores 1 day, not 0.
    """
    if df.empty:
        return pd.DataFrame(
            columns=[
                "customer_id", "recency_days", "frequency", "monetary",
                "r_score", "f_score", "m_score", "rfm_score", "segment", "segment_reason",
            ]
        )

    out = df.copy()
    out["last_purchase_date"] = pd.to_datetime(out["last_purchase_date"])

    if snapshot_date is None:
        snapshot_date = out["last_purchase_date"].max() + pd.Timedelta(days=1)

    out["recency_days"] = (snapshot_date - out["last_purchase_date"]).dt.days
    out["frequency"] = out["total_orders"].astype(int)
    out["monetary"] = out["total_spend"].astype(float)

    # Recency is inverted: fewer days since purchase = better = higher score.
    out["r_score"] = _score(out["recency_days"], quantiles, ascending=False)
    out["f_score"] = _score(out["frequency"], quantiles, ascending=True)
    out["m_score"] = _score(out["monetary"], quantiles, ascending=True)

    out["rfm_score"] = (
        out["r_score"].astype(str) + out["f_score"].astype(str) + out["m_score"].astype(str)
    )
    out["segment"] = out.apply(assign_segment, axis=1)
    out["segment_reason"] = out["segment"].map(SEGMENT_REASONS)

    logger.info(
        "Scored %s customers (snapshot=%s)",
        f"{len(out):,}",
        snapshot_date.date(),
    )
    return out[
        [
            "customer_id", "recency_days", "frequency", "monetary",
            "r_score", "f_score", "m_score", "rfm_score", "segment", "segment_reason",
        ]
    ]


def _score(series: pd.Series, quantiles: int = 5, *, ascending: bool = True) -> pd.Series:
    """Assign 1..`quantiles` scores by quantile rank.

    Ranking before binning is essential: Frequency is dominated by ties (most
    customers place exactly one order), which gives `pd.qcut` duplicate bin
    edges and makes it raise. Ranking with method="first" breaks the ties so the
    buckets are always well-defined, and the result still splits the population
    into equal-sized groups.
    """
    ranked = series.rank(method="first", ascending=ascending)

    # With fewer distinct values than buckets, fall back to as many as exist.
    effective = min(quantiles, int(ranked.nunique()))
    if effective < 2:
        return pd.Series(
            np.full(len(series), quantiles), index=series.index, dtype=int
        )

    labels = list(range(1, effective + 1))
    return pd.qcut(ranked, q=effective, labels=labels).astype(int)


def assign_segment(row: pd.Series) -> str:
    """Map an RFM score triple to a named segment.

    Rules are evaluated top to bottom; the first match wins, so the more
    specific segments are listed before the broader ones.
    """
    r = int(row["r_score"])
    f = int(row["f_score"])
    m = int(row["m_score"])
    # Frequency and monetary are combined into one "value" axis, the standard
    # simplification that keeps the rule table readable.
    fm = round((f + m) / 2)

    if r >= 4 and fm >= 4:
        return "Champions"
    if r >= 3 and fm >= 4:
        return "Loyal Customers"
    if r >= 4 and f <= 1:
        return "New Customers"
    if r >= 4 and fm >= 2:
        return "Potential Loyalists"
    if r <= 2 and fm >= 3:
        return "At-Risk"
    if r <= 2 and fm <= 2:
        return "Lost"
    return "Others"


def run(db_path: Path | str | None = None) -> pd.DataFrame:
    """Compute segments from the database and write them back to `customers`."""
    summary = customer_analytics.get_customer_summary(db_path)
    if summary.empty:
        logger.warning("No identified customers to segment")
        return summary

    quantiles = int(get_section("segmentation").get("quantiles", 5))
    rfm = compute_rfm(
        summary.rename(columns={"total_orders": "total_orders", "total_spend": "total_spend"}),
        quantiles=quantiles,
    )
    _persist(rfm, db_path)

    counts = rfm["segment"].value_counts().to_dict()
    logger.info("Segment distribution: %s", counts)
    return rfm


def _persist(rfm: pd.DataFrame, db_path: Path | str | None = None) -> None:
    """Write RFM columns onto the existing `customers` rows."""
    records = rfm[
        [
            "recency_days", "frequency", "monetary",
            "r_score", "f_score", "m_score", "rfm_score",
            "segment", "segment_reason", "customer_id",
        ]
    ].astype(object).values.tolist()

    with db.get_connection(db_path) as conn:
        conn.executemany(
            """
            UPDATE customers
               SET recency_days = ?, frequency = ?, monetary = ?,
                   r_score = ?, f_score = ?, m_score = ?, rfm_score = ?,
                   segment = ?, segment_reason = ?
             WHERE customer_id = ?
            """,
            records,
        )
    logger.info("Persisted segments for %s customers", f"{len(records):,}")
