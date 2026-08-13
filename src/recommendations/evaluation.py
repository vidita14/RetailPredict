"""Offline evaluation of the recommender (PRD Section 25).

Protocol: a time-based split. Each eligible customer's most recent invoice(s)
are held out, the recommender is rebuilt from *only* the earlier history, and we
check whether the held-out products surface in the top-K list.

Rebuilding against a separate training database — rather than filtering
predictions after the fact — is what makes this a genuine holdout: the
association rules and similarity matrix never see the test period.

All metrics reported here are calculated from the actual dataset. Any statement
about revenue impact would be a hypothetical estimate and is deliberately not
produced by this module.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pandas as pd

from src.database import db, load_to_sqlite
from src.recommendations import engine as engine_module
from src.recommendations import market_basket
from src.segmentation import rfm
from src.utils.config import EVALUATION_REPORT_PATH
from src.utils.logging import get_logger

logger = get_logger("recommendations.evaluation")


@dataclass
class EvaluationResult:
    """Metrics from one evaluation run."""

    k: int
    holdout_invoices: int
    customers_evaluated: int
    precision_at_k: float
    recall_at_k: float
    hit_rate_at_k: float
    coverage: float
    catalog_size: int
    products_recommended: int
    method_mix: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def split_train_test(
    transactions: pd.DataFrame, holdout_invoices: int = 1, min_invoices: int = 2
) -> tuple[pd.DataFrame, dict[str, set[str]]]:
    """Hold out each customer's most recent `holdout_invoices` invoices.

    Customers with fewer than `min_invoices` are left entirely in train: holding
    out their only order would leave nothing to learn from, and scoring them
    would measure the popularity fallback rather than the recommender.
    """
    identified = transactions[transactions["customer_id"].notna()].copy()
    identified["transaction_date"] = pd.to_datetime(identified["transaction_date"])

    # Rank each customer's invoices by recency (1 = most recent).
    invoice_dates = (
        identified.groupby(["customer_id", "invoice_no"], observed=True)["transaction_date"]
        .max()
        .reset_index()
    )
    invoice_dates["recency_rank"] = invoice_dates.groupby("customer_id")[
        "transaction_date"
    ].rank(method="first", ascending=False)

    invoice_counts = invoice_dates.groupby("customer_id").size()
    eligible = set(invoice_counts[invoice_counts >= min_invoices].index)

    held_out_invoices = set(
        invoice_dates[
            invoice_dates["customer_id"].isin(eligible)
            & (invoice_dates["recency_rank"] <= holdout_invoices)
        ]["invoice_no"]
    )

    test_mask = transactions["invoice_no"].isin(held_out_invoices)
    train = transactions[~test_mask].copy()

    test_rows = transactions[test_mask]
    test_by_customer = {
        str(customer_id): set(group["product_id"].astype(str))
        for customer_id, group in test_rows.groupby("customer_id", observed=True)
    }

    logger.info(
        "Split: %s train rows, %s test rows, %s customers with holdout",
        f"{len(train):,}",
        f"{len(test_rows):,}",
        f"{len(test_by_customer):,}",
    )
    return train, test_by_customer


def evaluate(
    k: int = 5,
    holdout_invoices: int = 1,
    min_invoices: int = 2,
    max_customers: int | None = None,
    db_path: Path | str | None = None,
) -> EvaluationResult:
    """Run the full offline evaluation and return the metrics."""
    transactions = db.run_query(
        """
        SELECT invoice_no, customer_id, product_id, transaction_date,
               quantity, unit_price, revenue, country
        FROM transactions
        """,
        db_path=db_path,
    )
    catalog_size = int(db.run_query("SELECT COUNT(*) AS n FROM products", db_path=db_path)["n"][0])

    train, test_by_customer = split_train_test(transactions, holdout_invoices, min_invoices)

    if not test_by_customer:
        return EvaluationResult(
            k=k, holdout_invoices=holdout_invoices, customers_evaluated=0,
            precision_at_k=0.0, recall_at_k=0.0, hit_rate_at_k=0.0, coverage=0.0,
            catalog_size=catalog_size, products_recommended=0,
            notes=["No customers had enough purchase history to hold out an invoice."],
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        train_db = Path(tmpdir) / "train.db"

        # Rebuild the full model stack against training data only.
        train_frame = train.rename(columns={"transaction_date": "invoice_date"})
        train_frame["invoice_date"] = pd.to_datetime(train_frame["invoice_date"])
        train_frame["description"] = train_frame["product_id"]  # names come from the real catalog

        load_to_sqlite.load(train_frame, train_db)
        rfm.run(train_db)
        market_basket.run(train_db)

        trained_engine = engine_module.RecommendationEngine(train_db)

        customers = list(test_by_customer)
        if max_customers:
            customers = customers[:max_customers]

        precisions: list[float] = []
        recalls: list[float] = []
        hits = 0
        recommended_products: set[str] = set()
        method_mix: dict[str, int] = {}

        for customer_id in customers:
            actual = test_by_customer[customer_id]
            recs = trained_engine.recommend(customer_id, k)
            predicted = [r.product_id for r in recs]
            recommended_products.update(predicted)
            for rec in recs:
                method_mix[rec.source_method] = method_mix.get(rec.source_method, 0) + 1

            matched = len(set(predicted) & actual)
            precisions.append(matched / k)
            recalls.append(matched / len(actual) if actual else 0.0)
            hits += 1 if matched else 0

        evaluated = len(customers)
        result = EvaluationResult(
            k=k,
            holdout_invoices=holdout_invoices,
            customers_evaluated=evaluated,
            precision_at_k=round(sum(precisions) / evaluated, 4),
            recall_at_k=round(sum(recalls) / evaluated, 4),
            hit_rate_at_k=round(hits / evaluated, 4),
            coverage=round(len(recommended_products) / catalog_size, 4) if catalog_size else 0.0,
            catalog_size=catalog_size,
            products_recommended=len(recommended_products),
            method_mix=method_mix,
        )

    logger.info(
        "Precision@%d=%.3f  Recall@%d=%.3f  HitRate@%d=%.3f  Coverage=%.3f (n=%s)",
        k, result.precision_at_k, k, result.recall_at_k, k, result.hit_rate_at_k,
        result.coverage, f"{evaluated:,}",
    )
    return result


def run(k: int = 5, db_path: Path | str | None = None) -> EvaluationResult:
    """Evaluate and write the report to `data/processed/evaluation_report.json`."""
    result = evaluate(k=k, db_path=db_path)
    EVALUATION_REPORT_PATH.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    logger.info("Wrote %s", EVALUATION_REPORT_PATH.name)
    return result
