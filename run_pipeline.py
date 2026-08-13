"""RetailPredict pipeline orchestrator — the single entry point (PRD Section 11).

    python run_pipeline.py

Stages run in dependency order; each is independently importable and testable.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from src.data import clean_data, transform_data, validate_schema
from src.database import load_to_sqlite
from src.recommendations import engine as recommendation_engine
from src.recommendations import evaluation, market_basket
from src.segmentation import rfm
from src.utils.config import (
    CLEAN_TRANSACTIONS_PATH,
    DATABASE_PATH,
    QUALITY_REPORT_PATH,
    ensure_directories,
)
from src.utils.logging import get_logger

logger = get_logger("pipeline")


def run(
    dataset_path: Path | str | None = None,
    db_path: Path | str | None = None,
    *,
    skip_evaluation: bool = False,
) -> int:
    """Run the full pipeline. Returns a process exit code."""
    started = time.perf_counter()
    ensure_directories()

    # --- Stage 1: ingest + validate -----------------------------------------
    logger.info("[1/7] Validating raw dataset")
    raw = validate_schema.load_raw(dataset_path)
    report = validate_schema.validate(raw)
    validate_schema.raise_for_report(report)
    canonical = validate_schema.rename_to_canonical(raw)

    # --- Stage 2: clean ------------------------------------------------------
    logger.info("[2/7] Cleaning")
    cleaned, cleaning_report = clean_data.clean(canonical)
    if cleaned.empty:
        raise ValueError(
            "Cleaning removed every row. Inspect the quality report to see which "
            "filter was responsible before re-running."
        )

    # --- Stage 3: transform --------------------------------------------------
    logger.info("[3/7] Transforming")
    transformed = transform_data.transform(cleaned)
    transformed.to_csv(CLEAN_TRANSACTIONS_PATH, index=False)
    logger.info("Wrote %s", CLEAN_TRANSACTIONS_PATH.name)

    quality_report = {
        "validation": report.to_dict(),
        "cleaning": cleaning_report.to_dict(),
    }
    QUALITY_REPORT_PATH.write_text(json.dumps(quality_report, indent=2), encoding="utf-8")
    logger.info("Wrote %s", QUALITY_REPORT_PATH.name)

    # --- Stage 4: load -------------------------------------------------------
    logger.info("[4/7] Loading into SQLite")
    load_to_sqlite.load(transformed, db_path)
    verification = load_to_sqlite.verify(db_path)

    if verification["orphan_product_rows"] or verification["orphan_customer_rows"]:
        logger.warning("Referential integrity issue: %s", verification)

    # --- Stage 5: segment ----------------------------------------------------
    logger.info("[5/7] Segmenting customers (RFM)")
    rfm.run(db_path)

    # --- Stage 6: mine rules + precompute recommendations --------------------
    logger.info("[6/7] Mining association rules and building recommendations")
    market_basket.run(db_path)
    recommendation_engine.run(db_path)

    # --- Stage 7: evaluate ---------------------------------------------------
    if skip_evaluation:
        logger.info("[7/7] Evaluation skipped (--skip-evaluation)")
    else:
        logger.info("[7/7] Evaluating recommender (time-based holdout)")
        evaluation.run(db_path=db_path)

    elapsed = time.perf_counter() - started
    counts = load_to_sqlite.db.get_table_counts(db_path)
    logger.info("Pipeline complete in %.1fs -> %s", elapsed, db_path or DATABASE_PATH)
    logger.info(
        "  customers=%s  products=%s  transactions=%s  rules=%s  recommendations=%s",
        f"{counts.get('customers', 0):,}",
        f"{counts.get('products', 0):,}",
        f"{counts.get('transactions', 0):,}",
        f"{counts.get('association_rules', 0):,}",
        f"{counts.get('recommendations', 0):,}",
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default=None, help="Override the CSV path from config.")
    parser.add_argument("--db", default=None, help="Override the SQLite output path.")
    parser.add_argument(
        "--skip-evaluation", action="store_true",
        help="Skip the holdout evaluation stage (the slowest step).",
    )
    args = parser.parse_args()

    try:
        return run(args.dataset, args.db, skip_evaluation=args.skip_evaluation)
    except (FileNotFoundError, ValueError, validate_schema.SchemaValidationError) as exc:
        logger.error("%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
