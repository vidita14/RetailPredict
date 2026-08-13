"""Schema shape and SQL analytics correctness, asserted against hand-computed
values on the fixture database."""

from __future__ import annotations

import pytest

from src.analytics import business_analytics, customer_analytics, product_analytics
from src.database import db, load_to_sqlite


def test_schema_has_expected_tables(fixture_db):
    counts = db.get_table_counts(fixture_db)
    for table in ("customers", "products", "transactions",
                  "association_rules", "recommendations"):
        assert table in counts


def test_all_indexes_are_created(fixture_db):
    verification = load_to_sqlite.verify(fixture_db)
    for index in (
        "idx_transactions_customer", "idx_transactions_product",
        "idx_transactions_date", "idx_transactions_invoice",
    ):
        assert index in verification["indexes"]


def test_foreign_keys_are_enforced(fixture_db):
    """PRAGMA foreign_keys must be ON, or the REFERENCES clauses do nothing."""
    with db.get_connection(fixture_db) as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_load_produces_no_orphan_rows(fixture_db):
    verification = load_to_sqlite.verify(fixture_db)
    assert verification["orphan_product_rows"] == 0
    assert verification["orphan_customer_rows"] == 0


def test_guest_transactions_load_with_null_customer_id(fixture_db):
    guests = db.run_query(
        "SELECT COUNT(*) AS n FROM transactions WHERE customer_id IS NULL", db_path=fixture_db
    )
    assert int(guests["n"][0]) == 1


def test_load_rejects_an_empty_dataframe(tmp_path, clean_df):
    with pytest.raises(ValueError, match="empty dataset"):
        load_to_sqlite.load(clean_df.iloc[0:0], tmp_path / "empty.db")


# --- Analytics: expected values computed by hand from the clean_df fixture ---

def test_customer_summary_totals(fixture_db):
    summary = customer_analytics.get_customer_summary(fixture_db)
    c1 = summary[summary["customer_id"] == "C1"].iloc[0]

    assert c1["total_spend"] == pytest.approx(60.0)   # 10 + 20 + 30
    assert c1["total_orders"] == 2                    # INV1, INV2
    assert c1["avg_order_value"] == pytest.approx(30.0)


def test_customer_summary_excludes_guest_rows(fixture_db):
    summary = customer_analytics.get_customer_summary(fixture_db)
    assert set(summary["customer_id"]) == {"C1", "C2"}


def test_kpis_include_guest_revenue_but_not_guest_customers(fixture_db):
    kpis = business_analytics.get_kpis(fixture_db)

    # 10 + 20 + 30 + 40 + 15 across all rows, guests included.
    assert kpis["total_revenue"] == pytest.approx(115.0)
    assert kpis["total_customers"] == 2      # C1, C2 — the guest is not a customer
    assert kpis["total_orders"] == 4         # INV1..INV4
    assert kpis["guest_revenue"] == pytest.approx(15.0)


def test_repeat_rate(fixture_db):
    """C1 has 2 orders, C2 has 1 -> half of identified customers are repeaters."""
    kpis = business_analytics.get_kpis(fixture_db)
    assert kpis["repeat_rate"] == pytest.approx(0.5)


def test_best_selling_products_ordered_by_revenue(fixture_db):
    products = product_analytics.get_best_selling_products(limit=10, db_path=fixture_db)

    # P2: 2x10 + 4x10 = 60;  P1: 2x5 + 6x5 = 40;  P3: 3x5 = 15
    assert products["product_id"].tolist() == ["P2", "P1", "P3"]
    assert products.iloc[0]["total_revenue"] == pytest.approx(60.0)


def test_monthly_revenue_groups_by_calendar_month(fixture_db):
    monthly = business_analytics.get_monthly_revenue(fixture_db)
    revenue_by_month = dict(zip(monthly["month"], monthly["revenue"]))

    assert revenue_by_month["2011-01"] == pytest.approx(30.0)   # INV1
    assert revenue_by_month["2011-02"] == pytest.approx(30.0)   # INV2
    assert revenue_by_month["2011-03"] == pytest.approx(55.0)   # INV3 + INV4


def test_co_occurrence_pairs_dedupe_and_exclude_self_pairs(fixture_db):
    """INV1 contains P1 and P2, so exactly one pair should be reported once."""
    pairs = product_analytics.get_co_occurrence_pairs(
        min_co_occurrence=1, limit=10, db_path=fixture_db
    )

    assert len(pairs) == 1
    row = pairs.iloc[0]
    assert {row["product_a"], row["product_b"]} == {"P1", "P2"}
    assert row["product_a"] < row["product_b"]


def test_new_vs_returning_classification(fixture_db):
    """C1's first purchase is in January, so January is New and February
    is Returning for that customer."""
    result = customer_analytics.get_new_vs_returning_by_month(fixture_db)
    lookup = {(r["month"], r["customer_type"]): r["customers"] for _, r in result.iterrows()}

    assert lookup.get(("2011-01", "New")) == 1
    assert lookup.get(("2011-02", "Returning")) == 1


def test_revenue_concentration_reaches_full_share(fixture_db):
    concentration = business_analytics.get_revenue_concentration(fixture_db)
    assert concentration["cumulative_revenue_share"].max() == pytest.approx(1.0)


def test_underperforming_products_respects_min_orders(fixture_db):
    """No product has 5+ orders in the fixture, so the list must be empty
    rather than surfacing single-order noise."""
    weak = business_analytics.get_underperforming_products(
        limit=10, min_orders=5, db_path=fixture_db
    )
    assert weak.empty


def test_run_query_rejects_a_missing_database(tmp_path):
    with pytest.raises(db.DatabaseError, match="Database not found"):
        db.run_query("SELECT 1", db_path=tmp_path / "nope.db")
