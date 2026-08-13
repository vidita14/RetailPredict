"""Cleaning and transformation correctness."""

from __future__ import annotations

import pandas as pd
import pytest

from src.data import clean_data, transform_data, validate_schema


def test_clean_removes_each_invalid_row_for_the_right_reason(raw_messy_df):
    cleaned, report = clean_data.clean(raw_messy_df)

    assert report.rows_before == 10
    # 5 removed: duplicate, cancellation, zero qty, negative price, bad date.
    assert report.rows_after == 5
    assert report.removed_by_reason["exact_duplicate_rows"] == 1
    assert report.removed_by_reason["cancelled_invoices"] == 1
    assert report.removed_by_reason["non_positive_quantity"] == 1
    assert report.removed_by_reason["non_positive_price"] == 1
    assert report.removed_by_reason["unparseable_date"] == 1


def test_clean_keeps_guest_rows_with_null_customer_id(raw_messy_df):
    cleaned, report = clean_data.clean(raw_messy_df)

    assert report.guest_transaction_rows == 1
    assert cleaned["customer_id"].isna().sum() == 1
    # The guest row's invoice survives — guest sales still count as product sales.
    assert "INV6" in set(cleaned["invoice_no"])


def test_clean_fills_missing_description_rather_than_dropping(raw_messy_df):
    cleaned, report = clean_data.clean(raw_messy_df)

    assert report.descriptions_filled == 1
    assert "INV7" in set(cleaned["invoice_no"])
    assert (cleaned["description"] == "Unknown Product").sum() == 1


def test_clean_normalizes_float_style_customer_ids():
    """The UCI dataset stores CustomerID as a float; "17850.0" and "17850" must
    not become two different customers."""
    frame = pd.DataFrame(
        [
            ("INV1", "P1", "Widget", 1, "2011-01-05 10:00", 5.0, "17850.0", "UK"),
            ("INV2", "P1", "Widget", 1, "2011-01-06 10:00", 5.0, "17850", "UK"),
        ],
        columns=[
            "invoice_no", "product_id", "description", "quantity",
            "invoice_date", "unit_price", "customer_id", "country",
        ],
    )
    cleaned, _ = clean_data.clean(frame)
    assert set(cleaned["customer_id"]) == {"17850"}


def test_clean_is_deterministic(raw_messy_df):
    first, _ = clean_data.clean(raw_messy_df)
    second, _ = clean_data.clean(raw_messy_df)
    pd.testing.assert_frame_equal(first, second)


def test_clean_does_not_mutate_its_input(raw_messy_df):
    before = raw_messy_df.copy()
    clean_data.clean(raw_messy_df)
    pd.testing.assert_frame_equal(raw_messy_df, before)


def test_revenue_is_quantity_times_price():
    frame = pd.DataFrame({"quantity": [2, 3], "unit_price": [5.0, 2.5]})
    result = transform_data.add_revenue(frame)
    assert result["revenue"].tolist() == [10.0, 7.5]


def test_quality_report_percentages_add_up(raw_messy_df):
    _, report = clean_data.clean(raw_messy_df)
    payload = report.to_dict()

    assert payload["rows_removed"] == payload["rows_before"] - payload["rows_after"]
    assert sum(payload["removed_by_reason"].values()) == payload["rows_removed"]


def test_build_customers_excludes_guests_and_materializes_totals(clean_df):
    customers = transform_data.build_customers(clean_df)

    assert set(customers["customer_id"]) == {"C1", "C2"}
    c1 = customers[customers["customer_id"] == "C1"].iloc[0]
    assert c1["total_orders"] == 2          # INV1 and INV2
    assert c1["total_spend"] == pytest.approx(60.0)


def test_build_products_picks_the_most_common_description():
    frame = pd.DataFrame(
        {
            "product_id": ["P1", "P1", "P1", "P2"],
            "description": ["Widget", "Widget", "WIDGET typo", "Gadget"],
        }
    )
    products = transform_data.build_products(frame)
    assert products[products["product_id"] == "P1"]["product_name"].iloc[0] == "Widget"


def test_validate_reports_missing_columns():
    frame = pd.DataFrame({"InvoiceNo": ["1"], "Quantity": [1]})
    report = validate_schema.validate(frame)

    assert not report.is_valid
    assert any("customer_id" in column for column in report.missing_columns)


def test_raise_for_report_halts_on_missing_columns():
    frame = pd.DataFrame({"InvoiceNo": ["1"]})
    report = validate_schema.validate(frame)

    with pytest.raises(validate_schema.SchemaValidationError, match="missing required columns"):
        validate_schema.raise_for_report(report)


def test_raise_for_report_halts_on_empty_dataset(raw_messy_df):
    report = validate_schema.validate(raw_messy_df.iloc[0:0])
    with pytest.raises(validate_schema.SchemaValidationError, match="empty"):
        validate_schema.raise_for_report(report)
