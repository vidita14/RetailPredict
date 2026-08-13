"""Central configuration loader.

Every path in the project is derived from PROJECT_ROOT so the pipeline behaves
identically regardless of the working directory it is invoked from (the
dashboard runs from `dashboard/`, the pipeline from the repo root).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]

CONFIG_PATH = PROJECT_ROOT / "config" / "column_mapping.yaml"
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
DATABASE_PATH = PROJECT_ROOT / "database" / "retailpredict.db"
SCHEMA_PATH = PROJECT_ROOT / "src" / "database" / "schema.sql"

CLEAN_TRANSACTIONS_PATH = PROCESSED_DIR / "clean_transactions.csv"
QUALITY_REPORT_PATH = PROCESSED_DIR / "quality_report.json"
EVALUATION_REPORT_PATH = PROCESSED_DIR / "evaluation_report.json"

# Canonical column names used everywhere downstream of ingestion.
CANONICAL_COLUMNS = [
    "invoice_no",
    "product_id",
    "description",
    "quantity",
    "invoice_date",
    "unit_price",
    "customer_id",
    "country",
]


@lru_cache(maxsize=1)
def load_config(path: Path | None = None) -> dict[str, Any]:
    """Load `config/column_mapping.yaml`. Cached; call `load_config.cache_clear()` in tests."""
    config_path = Path(path) if path else CONFIG_PATH
    if not config_path.exists():
        raise FileNotFoundError(
            f"Config file not found at {config_path}. "
            "Expected `config/column_mapping.yaml` at the project root."
        )
    with config_path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def get_dataset_path() -> Path:
    """Absolute path to the raw CSV named in the config."""
    raw = load_config()["dataset"]["path"]
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def get_column_mapping() -> dict[str, str]:
    """Canonical name -> raw CSV column name."""
    return dict(load_config()["columns"])


def get_section(name: str) -> dict[str, Any]:
    """Return a top-level config section, or an empty dict if absent."""
    return dict(load_config().get(name) or {})


def ensure_directories() -> None:
    """Create the generated-output directories if they do not exist."""
    for directory in (RAW_DIR, PROCESSED_DIR, DATABASE_PATH.parent):
        directory.mkdir(parents=True, exist_ok=True)
