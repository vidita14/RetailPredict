"""Shared fixtures: small synthetic datasets with hand-computable expected values."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data import transform_data  # noqa: E402
from src.database import load_to_sqlite  # noqa: E402


@pytest.fixture
def raw_messy_df() -> pd.DataFrame:
    """A canonical-column frame containing one of every quality problem.

    Row-by-row, so the expected cleaning outcome can be reasoned about directly:
      0,1  valid rows for customer C1
      2    valid row for customer C2
      3    exact duplicate of row 0        -> removed
      4    cancelled invoice (C-prefix)    -> removed
      5    zero quantity                   -> removed
      6    negative unit price             -> removed
      7    unparseable date                -> removed
      8    guest row (no customer id)      -> KEPT, customer_id null
      9    missing description             -> KEPT, filled with placeholder
    """
    return pd.DataFrame(
        [
            ("INV1", "P1", "Widget",  2, "2011-01-05 10:00", 5.0,  "C1", "UK"),
            ("INV1", "P2", "Gadget",  1, "2011-01-05 10:00", 10.0, "C1", "UK"),
            ("INV2", "P1", "Widget",  3, "2011-02-10 11:00", 5.0,  "C2", "UK"),
            ("INV1", "P1", "Widget",  2, "2011-01-05 10:00", 5.0,  "C1", "UK"),
            ("C900", "P1", "Widget", -2, "2011-03-01 09:00", 5.0,  "C1", "UK"),
            ("INV3", "P2", "Gadget",  0, "2011-03-02 09:00", 10.0, "C2", "UK"),
            ("INV4", "P1", "Widget",  1, "2011-03-03 09:00", -1.0, "C2", "UK"),
            ("INV5", "P1", "Widget",  1, "not a date",      5.0,  "C1", "UK"),
            ("INV6", "P2", "Gadget",  4, "2011-04-01 12:00", 10.0, None, "UK"),
            ("INV7", "P3", None,      1, "2011-04-02 12:00", 7.0,  "C2", "France"),
        ],
        columns=[
            "invoice_no", "product_id", "description", "quantity",
            "invoice_date", "unit_price", "customer_id", "country",
        ],
    )


@pytest.fixture
def clean_df() -> pd.DataFrame:
    """A small already-clean transaction set with known aggregate totals.

    C1: 2 invoices, revenue 10 + 20 + 30 = 60
    C2: 1 invoice,  revenue 40
    Guest: 1 row,   revenue 15 (excluded from customer-level figures)
    """
    frame = pd.DataFrame(
        [
            ("INV1", "P1", "Widget", 2, "2011-01-05 10:00", 5.0,  "C1", "UK"),
            ("INV1", "P2", "Gadget", 2, "2011-01-05 10:00", 10.0, "C1", "UK"),
            ("INV2", "P1", "Widget", 6, "2011-02-10 11:00", 5.0,  "C1", "UK"),
            ("INV3", "P2", "Gadget", 4, "2011-03-10 11:00", 10.0, "C2", "France"),
            ("INV4", "P3", "Doodad", 3, "2011-03-11 11:00", 5.0,  None, "UK"),
        ],
        columns=[
            "invoice_no", "product_id", "description", "quantity",
            "invoice_date", "unit_price", "customer_id", "country",
        ],
    )
    frame["invoice_date"] = pd.to_datetime(frame["invoice_date"])
    return transform_data.transform(frame)


@pytest.fixture
def fixture_db(tmp_path: Path, clean_df: pd.DataFrame) -> Path:
    """A populated SQLite database built from `clean_df`."""
    db_path = tmp_path / "test.db"
    load_to_sqlite.load(clean_df, db_path)
    return db_path
