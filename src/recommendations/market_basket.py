"""Market basket analysis via mlxtend Apriori (PRD Section 15, tier 1).

SQL supplies the invoice-level basket data; mlxtend does the statistical
scoring (support / confidence / lift). Mined rules are persisted to the
`association_rules` table so the dashboard never re-runs Apriori at render time.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from mlxtend.frequent_patterns import apriori, association_rules

from src.database import db
from src.utils.config import get_section
from src.utils.logging import get_logger

logger = get_logger("recommendations.market_basket")


def build_baskets(
    max_products: int = 300, db_path: Path | str | None = None
) -> pd.DataFrame:
    """One-hot invoice x product matrix, restricted to the most popular products.

    Apriori is combinatorial in the number of items, so capping the catalog to
    the top `max_products` by invoice frequency is what keeps runtime bounded on
    a full-size dataset (PRD Section 32 risk mitigation).
    """
    basket_rows = db.run_query(
        """
        WITH top_products AS (
            SELECT product_id
            FROM transactions
            GROUP BY product_id
            ORDER BY COUNT(DISTINCT invoice_no) DESC
            LIMIT ?
        )
        SELECT DISTINCT t.invoice_no, t.product_id
        FROM transactions t
        JOIN top_products tp ON t.product_id = tp.product_id
        """,
        (max_products,),
        db_path,
    )

    if basket_rows.empty:
        logger.warning("No basket data available")
        return pd.DataFrame()

    basket = (
        basket_rows.assign(present=True)
        .pivot_table(
            index="invoice_no", columns="product_id", values="present",
            fill_value=False, aggfunc="first",
        )
        .astype(bool)
    )
    logger.info("Built basket matrix: %s invoices x %s products", *basket.shape)
    return basket


def mine_rules(
    basket: pd.DataFrame,
    min_support: float = 0.02,
    min_confidence: float = 0.3,
    min_lift: float = 1.0,
) -> pd.DataFrame:
    """Mine 1-to-1 association rules.

    Rules are restricted to a single antecedent and single consequent: multi-item
    rules are harder to look up per product and produce reason text a business
    user cannot parse ("bought with A and C and F..."), which conflicts with the
    explainability requirement.
    """
    if basket.empty:
        return _empty_rules()

    itemsets = apriori(basket, min_support=min_support, use_colnames=True)
    if itemsets.empty:
        logger.warning(
            "No itemsets met min_support=%.3f; try lowering it in config.", min_support
        )
        return _empty_rules()

    rules = association_rules(itemsets, metric="confidence", min_threshold=min_confidence)
    if rules.empty:
        logger.warning("No rules met min_confidence=%.2f", min_confidence)
        return _empty_rules()

    rules = rules[
        (rules["antecedents"].apply(len) == 1)
        & (rules["consequents"].apply(len) == 1)
        & (rules["lift"] >= min_lift)
    ].copy()

    if rules.empty:
        return _empty_rules()

    rules["antecedent"] = rules["antecedents"].apply(lambda s: next(iter(s)))
    rules["consequent"] = rules["consequents"].apply(lambda s: next(iter(s)))

    out = rules[["antecedent", "consequent", "support", "confidence", "lift"]].sort_values(
        "lift", ascending=False
    ).reset_index(drop=True)

    logger.info("Mined %s association rules", f"{len(out):,}")
    return out


def _empty_rules() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["antecedent", "consequent", "support", "confidence", "lift"]
    )


def run(db_path: Path | str | None = None) -> pd.DataFrame:
    """Build baskets, mine rules, and persist them. Returns the rules."""
    cfg = get_section("recommendations")

    basket = build_baskets(int(cfg.get("max_products_for_apriori", 300)), db_path)
    rules = mine_rules(
        basket,
        min_support=float(cfg.get("min_support", 0.02)),
        min_confidence=float(cfg.get("min_confidence", 0.3)),
        min_lift=float(cfg.get("min_lift", 1.0)),
    )

    db.execute("DELETE FROM association_rules", db_path=db_path)
    if not rules.empty:
        db.write_dataframe(rules, "association_rules", db_path=db_path)
    return rules


def load_rules(db_path: Path | str | None = None) -> pd.DataFrame:
    """Read persisted rules, best lift first."""
    return db.run_query(
        "SELECT antecedent, consequent, support, confidence, lift "
        "FROM association_rules ORDER BY lift DESC",
        db_path=db_path,
    )
