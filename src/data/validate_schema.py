"""Schema validation for the raw ingested CSV.

Pure functions: `validate` inspects a DataFrame and returns a report; it never
mutates the input or writes to disk (PRD Section 22).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from src.utils.config import (
    CANONICAL_COLUMNS,
    get_column_mapping,
    get_dataset_path,
    load_config,
)
from src.utils.logging import get_logger

logger = get_logger("data.validate")


class SchemaValidationError(Exception):
    """Raised when the raw dataset cannot support the pipeline."""


@dataclass
class ValidationReport:
    """Structured result of validating a raw DataFrame."""

    total_rows: int
    total_columns: int
    missing_columns: list[str] = field(default_factory=list)
    column_stats: dict[str, dict[str, Any]] = field(default_factory=dict)
    issues: dict[str, int] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        return not self.missing_columns and self.total_rows > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_rows": self.total_rows,
            "total_columns": self.total_columns,
            "missing_columns": self.missing_columns,
            "column_stats": self.column_stats,
            "issues": self.issues,
            "is_valid": self.is_valid,
        }


def load_raw(path: Path | str | None = None) -> pd.DataFrame:
    """Read the raw CSV named in config (or an explicit path).

    Fails fast with an actionable message if the file is absent (PRD Section 23).
    """
    dataset_path = Path(path) if path else get_dataset_path()
    if not dataset_path.exists():
        raise FileNotFoundError(
            f"Dataset not found at {dataset_path}.\n"
            f"Place your retail CSV in `data/raw/` and set `dataset.path` in "
            f"`config/column_mapping.yaml` to match its filename."
        )

    encoding = load_config()["dataset"].get("encoding", "utf-8")
    logger.info("Reading %s (encoding=%s)", dataset_path.name, encoding)

    read_kwargs: dict[str, Any] = {"encoding": encoding, "dtype": str}
    if dataset_path.suffix.lower() in {".xlsx", ".xls"}:
        df = pd.read_excel(dataset_path, dtype=str)
    else:
        df = pd.read_csv(dataset_path, **read_kwargs)

    logger.info("Read %s rows x %s columns", f"{len(df):,}", df.shape[1])
    return df


def rename_to_canonical(df: pd.DataFrame, mapping: dict[str, str] | None = None) -> pd.DataFrame:
    """Rename raw CSV headers to canonical internal names.

    Keeps the pipeline dataset-agnostic: only this function knows about the raw
    column names (PRD Section 10).
    """
    mapping = mapping or get_column_mapping()
    # mapping is canonical -> raw; pandas.rename wants raw -> canonical.
    inverted = {raw: canonical for canonical, raw in mapping.items()}
    renamed = df.rename(columns=inverted)
    known = [c for c in CANONICAL_COLUMNS if c in renamed.columns]
    return renamed[known].copy()


def validate(df: pd.DataFrame, mapping: dict[str, str] | None = None) -> ValidationReport:
    """Inspect a *raw* DataFrame and report structural + quality problems.

    Does not raise; the caller decides whether to halt. `raise_for_report`
    turns an invalid report into an exception.
    """
    mapping = mapping or get_column_mapping()
    present = set(df.columns)

    missing = [
        f"{canonical} (expected CSV column '{raw}')"
        for canonical, raw in mapping.items()
        if raw not in present
    ]

    report = ValidationReport(
        total_rows=len(df),
        total_columns=df.shape[1],
        missing_columns=missing,
    )

    if missing:
        return report

    canonical_df = rename_to_canonical(df, mapping)

    for column in canonical_df.columns:
        series = canonical_df[column]
        null_count = int(series.isna().sum())
        report.column_stats[column] = {
            "dtype": str(series.dtype),
            "null_count": null_count,
            "null_pct": round(100 * null_count / len(series), 2) if len(series) else 0.0,
            "unique_count": int(series.nunique(dropna=True)),
        }

    report.issues = _detect_issues(canonical_df)
    return report


def _detect_issues(df: pd.DataFrame) -> dict[str, int]:
    """Count the quality problems the cleaning stage will act on."""
    prefix = load_config()["cleaning"]["cancellation_prefix"]

    quantity = pd.to_numeric(df["quantity"], errors="coerce")
    unit_price = pd.to_numeric(df["unit_price"], errors="coerce")
    parsed_dates = pd.to_datetime(df["invoice_date"], errors="coerce", format="mixed")

    return {
        "duplicate_rows": int(df.duplicated().sum()),
        "missing_customer_id": int(df["customer_id"].isna().sum()),
        "missing_description": int(df["description"].isna().sum()),
        "cancelled_invoices": int(
            df["invoice_no"].astype(str).str.upper().str.startswith(prefix.upper()).sum()
        ),
        "non_positive_quantity": int((quantity <= 0).sum()),
        "non_positive_price": int((unit_price <= 0).sum()),
        "unparseable_quantity": int(quantity.isna().sum() - df["quantity"].isna().sum()),
        "unparseable_price": int(unit_price.isna().sum() - df["unit_price"].isna().sum()),
        "unparseable_dates": int(parsed_dates.isna().sum()),
    }


def raise_for_report(report: ValidationReport) -> None:
    """Halt the pipeline with an explicit list of what is wrong (PRD Section 23)."""
    if report.total_rows == 0:
        raise SchemaValidationError(
            "Dataset is empty (0 rows). Refusing to build an empty database."
        )
    if report.missing_columns:
        listed = "\n  - ".join(report.missing_columns)
        raise SchemaValidationError(
            "Raw dataset is missing required columns:\n  - "
            f"{listed}\n"
            "Update the `columns:` mapping in `config/column_mapping.yaml` so each "
            "canonical name points at the correct column in your CSV."
        )
