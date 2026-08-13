"""Deterministic cleaning pipeline (PRD Section 8.B).

`clean` is a pure function: DataFrame in, cleaned DataFrame + quality report out.
No file I/O happens here — `run_pipeline.py` owns persistence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from src.utils.config import get_section
from src.utils.logging import get_logger

logger = get_logger("data.clean")


@dataclass
class CleaningReport:
    """Before/after row accounting, broken down by removal reason."""

    rows_before: int = 0
    rows_after: int = 0
    removed_by_reason: dict[str, int] = field(default_factory=dict)
    guest_transaction_rows: int = 0
    descriptions_filled: int = 0

    @property
    def rows_removed(self) -> int:
        return self.rows_before - self.rows_after

    @property
    def pct_removed(self) -> float:
        if not self.rows_before:
            return 0.0
        return round(100 * self.rows_removed / self.rows_before, 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rows_before": self.rows_before,
            "rows_after": self.rows_after,
            "rows_removed": self.rows_removed,
            "pct_removed": self.pct_removed,
            "removed_by_reason": self.removed_by_reason,
            "removed_by_reason_pct": {
                reason: round(100 * count / self.rows_before, 2) if self.rows_before else 0.0
                for reason, count in self.removed_by_reason.items()
            },
            "guest_transaction_rows": self.guest_transaction_rows,
            "descriptions_filled": self.descriptions_filled,
        }


def clean(df: pd.DataFrame) -> tuple[pd.DataFrame, CleaningReport]:
    """Clean a canonical-column DataFrame.

    Order matters: coercions run before filters so that unparseable values are
    attributed to the right removal reason rather than silently surviving.
    """
    cleaning_cfg = get_section("cleaning")
    prefix = cleaning_cfg.get("cancellation_prefix", "C")
    unknown_name = cleaning_cfg.get("unknown_product_name", "Unknown Product")
    keep_guests = cleaning_cfg.get("keep_guest_transactions", True)

    report = CleaningReport(rows_before=len(df))
    working = df.copy()

    # --- Type coercion -------------------------------------------------------
    working["invoice_no"] = working["invoice_no"].astype(str).str.strip()
    working["product_id"] = working["product_id"].astype(str).str.strip().str.upper()
    working["country"] = working["country"].astype(str).str.strip()
    working["quantity"] = pd.to_numeric(working["quantity"], errors="coerce")
    working["unit_price"] = pd.to_numeric(working["unit_price"], errors="coerce")
    working["invoice_date"] = pd.to_datetime(
        working["invoice_date"], errors="coerce", format="mixed"
    )

    # CustomerID arrives as a float-like string ("17850.0") in the UCI dataset;
    # normalize to a clean integer-style string so joins are stable.
    working["customer_id"] = _normalize_customer_id(working["customer_id"])

    # --- Missing descriptions are filled, never dropped ----------------------
    missing_desc = working["description"].isna() | (
        working["description"].astype(str).str.strip() == ""
    )
    report.descriptions_filled = int(missing_desc.sum())
    working["description"] = (
        working["description"].astype(str).str.strip().mask(missing_desc, unknown_name)
    )

    # --- Sequential filtering, each attributed to a reason -------------------
    def drop(mask: pd.Series, reason: str) -> None:
        """Drop rows where `mask` is True and record how many were removed."""
        nonlocal working
        removed = int(mask.sum())
        if removed:
            working = working.loc[~mask].copy()
        report.removed_by_reason[reason] = report.removed_by_reason.get(reason, 0) + removed

    drop(working.duplicated(keep="first"), "exact_duplicate_rows")
    drop(
        working["invoice_no"].str.upper().str.startswith(prefix.upper()),
        "cancelled_invoices",
    )
    drop(working["invoice_date"].isna(), "unparseable_date")
    drop(working["quantity"].isna() | (working["quantity"] <= 0), "non_positive_quantity")
    drop(working["unit_price"].isna() | (working["unit_price"] <= 0), "non_positive_price")
    drop(
        working["product_id"].isna() | working["product_id"].isin({"", "NAN", "NONE"}),
        "missing_product_id",
    )

    # --- Guest transactions --------------------------------------------------
    # Rows without a CustomerID stay in the dataset (they are valid product-level
    # sales) but carry a null customer_id so customer analytics can exclude them.
    guest_mask = working["customer_id"].isna()
    report.guest_transaction_rows = int(guest_mask.sum())
    if not keep_guests:
        drop(guest_mask, "missing_customer_id")

    working["quantity"] = working["quantity"].astype(int)
    working["unit_price"] = working["unit_price"].astype(float)
    working = working.reset_index(drop=True)

    report.rows_after = len(working)
    logger.info(
        "Cleaned %s -> %s rows (%.2f%% removed, %s guest rows retained)",
        f"{report.rows_before:,}",
        f"{report.rows_after:,}",
        report.pct_removed,
        f"{report.guest_transaction_rows:,}",
    )
    return working, report


def _normalize_customer_id(series: pd.Series) -> pd.Series:
    """Coerce CustomerID to a stable string ID, or NaN for guest transactions.

    Handles the UCI dataset's float representation ("17850.0" -> "17850") so the
    same customer never splits across two ID spellings.
    """
    text = series.astype(str).str.strip()
    text = text.mask(text.isin({"", "nan", "NaN", "None", "NA", "<NA>"}))

    numeric = pd.to_numeric(text, errors="coerce")
    # Integral floats become plain integers; anything non-numeric keeps its
    # original string form (supports datasets with alphanumeric customer IDs).
    normalized = numeric.astype("Float64").round(0).astype("Int64").astype("string")
    return normalized.fillna(text.astype("string")).replace({pd.NA: None})
