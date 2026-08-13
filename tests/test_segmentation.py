"""RFM scoring and segment-assignment rules."""

from __future__ import annotations

import pandas as pd
import pytest

from src.segmentation import rfm


def _customers(n: int) -> pd.DataFrame:
    """n customers with strictly increasing recency, frequency, and spend."""
    return pd.DataFrame(
        {
            "customer_id": [f"C{i}" for i in range(n)],
            "last_purchase_date": pd.date_range("2011-01-01", periods=n, freq="D"),
            "total_orders": range(1, n + 1),
            "total_spend": [100.0 * (i + 1) for i in range(n)],
        }
    )


def test_quintile_scores_span_one_to_five():
    result = rfm.compute_rfm(_customers(50))
    for column in ("r_score", "f_score", "m_score"):
        assert result[column].min() == 1
        assert result[column].max() == 5


def test_recency_score_is_inverted():
    """The most recent buyer must score 5 on recency, the stalest 1."""
    result = rfm.compute_rfm(_customers(50)).set_index("customer_id")

    # C49 has the latest last_purchase_date -> lowest recency_days -> best score.
    assert result.loc["C49", "r_score"] == 5
    assert result.loc["C0", "r_score"] == 1
    assert result.loc["C49", "recency_days"] < result.loc["C0", "recency_days"]


def test_scoring_survives_heavily_tied_frequency():
    """The real-data failure mode: most customers place exactly one order, which
    gives pd.qcut duplicate bin edges unless ranks break the ties first."""
    frame = pd.DataFrame(
        {
            "customer_id": [f"C{i}" for i in range(100)],
            "last_purchase_date": pd.date_range("2011-01-01", periods=100, freq="D"),
            "total_orders": [1] * 95 + [2, 3, 4, 5, 6],   # 95% identical
            "total_spend": [50.0] * 95 + [10.0, 20.0, 30.0, 40.0, 50.0],
        }
    )
    result = rfm.compute_rfm(frame)

    assert len(result) == 100
    assert result["f_score"].between(1, 5).all()
    assert result["segment"].notna().all()


def test_every_customer_receives_a_segment_and_a_reason():
    result = rfm.compute_rfm(_customers(60))

    assert result["segment"].notna().all()
    assert result["segment_reason"].notna().all()
    assert (result["segment_reason"].str.len() > 0).all()


def test_single_customer_does_not_crash_scoring():
    result = rfm.compute_rfm(_customers(1))
    assert len(result) == 1
    assert result["segment"].notna().all()


def test_empty_input_returns_empty_frame_with_schema():
    result = rfm.compute_rfm(pd.DataFrame())
    assert result.empty
    assert "segment" in result.columns


def test_rfm_score_is_the_concatenated_triple():
    result = rfm.compute_rfm(_customers(50)).iloc[0]
    expected = f"{result['r_score']}{result['f_score']}{result['m_score']}"
    assert result["rfm_score"] == expected


@pytest.mark.parametrize(
    "r, f, m, expected",
    [
        (5, 5, 5, "Champions"),           # best on every axis
        (4, 4, 4, "Champions"),           # boundary: lowest scores still Champions
        (3, 5, 5, "Loyal Customers"),     # buys often, slightly less recent
        (5, 1, 1, "New Customers"),       # just arrived, no repeat yet
        (5, 1, 5, "New Customers"),       # one big first order is still new
        (4, 3, 3, "Potential Loyalists"), # recent, middling value
        (1, 5, 5, "At-Risk"),             # was valuable, has gone quiet
        (2, 4, 4, "At-Risk"),
        (1, 1, 1, "Lost"),                # gone, and never valuable
        (2, 2, 2, "Lost"),
        (3, 2, 2, "Others"),              # middle of every axis
    ],
)
def test_segment_rules_at_boundaries(r, f, m, expected):
    row = pd.Series({"r_score": r, "f_score": f, "m_score": m})
    assert rfm.assign_segment(row) == expected


def test_segment_rules_cover_every_possible_score_combination():
    """No combination of 1-5 scores may fall through without a segment."""
    for r in range(1, 6):
        for f in range(1, 6):
            for m in range(1, 6):
                row = pd.Series({"r_score": r, "f_score": f, "m_score": m})
                segment = rfm.assign_segment(row)
                assert segment in rfm.SEGMENT_REASONS


def test_run_persists_segments_to_the_database(fixture_db):
    from src.database import db

    rfm.run(fixture_db)
    customers = db.run_query("SELECT customer_id, segment, rfm_score FROM customers",
                             db_path=fixture_db)

    assert customers["segment"].notna().all()
    assert customers["rfm_score"].notna().all()
