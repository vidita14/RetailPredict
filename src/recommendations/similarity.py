"""Item-item collaborative similarity (PRD Section 15, tier 2).

Builds a customer x product interaction matrix from purchase counts and scores
products by cosine similarity. Used as backfill when association rules do not
produce enough candidates.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity

from src.database import db
from src.utils.config import get_section
from src.utils.logging import get_logger

logger = get_logger("recommendations.similarity")


@dataclass
class ItemSimilarity:
    """Item-item cosine similarity matrix with its product-id index."""

    matrix: np.ndarray
    product_ids: list[str]

    def __post_init__(self) -> None:
        self._index = {pid: i for i, pid in enumerate(self.product_ids)}

    @property
    def is_empty(self) -> bool:
        return self.matrix.size == 0

    def similar_to(self, product_id: str, top_n: int = 10) -> list[tuple[str, float]]:
        """Most similar products to one product, excluding itself."""
        idx = self._index.get(str(product_id))
        if idx is None:
            return []
        scores = self.matrix[idx].copy()
        scores[idx] = -1.0  # never recommend the seed product back
        top = np.argsort(scores)[::-1][:top_n]
        return [(self.product_ids[i], float(scores[i])) for i in top if scores[i] > 0]

    def score_against_basket(
        self, product_ids: list[str], exclude: set[str] | None = None, top_n: int = 20
    ) -> list[tuple[str, float, str]]:
        """Score every product against a customer's purchased set.

        A candidate's score is its best similarity to any owned product, and the
        owned product responsible is returned alongside it so the recommendation
        can explain which purchase drove it.
        """
        owned_idx = [self._index[p] for p in map(str, product_ids) if p in self._index]
        if not owned_idx:
            return []

        exclude = {str(p) for p in (exclude or set())}
        # For each candidate, take the maximum similarity across owned items
        # (rather than the mean) so a strong match to one item is not diluted by
        # unrelated purchases elsewhere in the basket.
        submatrix = self.matrix[owned_idx]          # (owned, all_products)
        best_scores = submatrix.max(axis=0)
        best_source = submatrix.argmax(axis=0)

        results: list[tuple[str, float, str]] = []
        for candidate_idx in np.argsort(best_scores)[::-1]:
            product_id = self.product_ids[candidate_idx]
            score = float(best_scores[candidate_idx])
            if score <= 0 or product_id in exclude:
                continue
            source_product = self.product_ids[owned_idx[int(best_source[candidate_idx])]]
            results.append((product_id, score, source_product))
            if len(results) >= top_n:
                break
        return results


def build_interaction_matrix(
    max_products: int = 1500, db_path: Path | str | None = None
) -> pd.DataFrame:
    """Customer x product matrix of purchase quantities.

    Only identified customers contribute — guest rows have no customer identity
    to correlate products across.
    """
    rows = db.run_query(
        """
        WITH top_products AS (
            SELECT product_id
            FROM transactions
            GROUP BY product_id
            ORDER BY COUNT(DISTINCT invoice_no) DESC
            LIMIT ?
        )
        SELECT t.customer_id, t.product_id, SUM(t.quantity) AS quantity
        FROM transactions t
        JOIN top_products tp ON t.product_id = tp.product_id
        WHERE t.customer_id IS NOT NULL
        GROUP BY t.customer_id, t.product_id
        """,
        (max_products,),
        db_path,
    )

    if rows.empty:
        return pd.DataFrame()

    matrix = rows.pivot_table(
        index="customer_id", columns="product_id", values="quantity", fill_value=0
    )
    logger.info("Interaction matrix: %s customers x %s products", *matrix.shape)
    return matrix


def build(db_path: Path | str | None = None) -> ItemSimilarity:
    """Compute the item-item cosine similarity matrix."""
    cfg = get_section("recommendations")
    interactions = build_interaction_matrix(
        int(cfg.get("max_products_for_similarity", 1500)), db_path
    )

    if interactions.empty:
        logger.warning("No interaction data; similarity tier disabled")
        return ItemSimilarity(matrix=np.empty((0, 0)), product_ids=[])

    # Transpose so rows are products: cosine over customer vectors means two
    # products are similar when the same customers buy both.
    item_vectors = interactions.T.to_numpy(dtype=float)
    matrix = cosine_similarity(item_vectors)
    np.fill_diagonal(matrix, 0.0)

    product_ids = [str(p) for p in interactions.columns]
    logger.info("Built %sx%s item similarity matrix", len(product_ids), len(product_ids))
    return ItemSimilarity(matrix=matrix, product_ids=product_ids)
