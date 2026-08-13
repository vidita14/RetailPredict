"""Hybrid recommendation engine (PRD Section 15, Appendix D).

Merges three tiers — association rules, item similarity, popularity fallback —
into a single ranked list where every entry carries the method and the specific
metric that produced it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from src.database import db
from src.recommendations import market_basket, popularity, similarity
from src.utils.config import get_section
from src.utils.logging import get_logger

logger = get_logger("recommendations.engine")

# Tier weights. Applied to each method's normalized 0-1 score so that a strong
# association rule outranks a strong similarity match, which in turn outranks a
# popularity backfill — while ranking *within* each tier stays intact.
METHOD_WEIGHTS = {
    "association_rule": 1.00,
    "product_similarity": 0.85,
    "popularity_fallback": 0.50,
}


@dataclass
class Recommendation:
    """A single explained recommendation (PRD Section 22)."""

    product_id: str
    product_name: str
    score: float
    source_method: str
    reason_text: str

    def to_dict(self) -> dict:
        return asdict(self)


class RecommendationEngine:
    """Holds the mined rules and similarity matrix so they are computed once.

    Building these per call would re-run Apriori on every dashboard interaction;
    the engine is constructed once and reused.
    """

    def __init__(self, db_path: Path | str | None = None):
        self.db_path = db_path
        cfg = get_section("recommendations")
        self.top_k = int(cfg.get("top_k", 5))
        self.recent_considered = int(cfg.get("recent_products_considered", 5))

        self.rules = market_basket.load_rules(db_path)
        self.similarity = similarity.build(db_path)
        self.product_names = self._load_product_names()

        logger.info(
            "Engine ready: %s rules, %s products in similarity matrix",
            f"{len(self.rules):,}",
            len(self.similarity.product_ids),
        )

    def _load_product_names(self) -> dict[str, str]:
        products = db.run_query(
            "SELECT product_id, product_name FROM products", db_path=self.db_path
        )
        return dict(zip(products["product_id"].astype(str), products["product_name"]))

    def name_of(self, product_id: str) -> str:
        """Product name, falling back to the raw ID for products no longer in
        the catalog (PRD Section 23: skip and warn, never crash)."""
        name = self.product_names.get(str(product_id))
        if name is None:
            logger.warning("Unknown product_id %s referenced in recommendations", product_id)
            return str(product_id)
        return name

    def recommend(self, customer_id: str, k: int | None = None) -> list[Recommendation]:
        """Return up to `k` ranked, explained recommendations for one customer."""
        k = k or self.top_k
        customer = db.get_customer(customer_id, self.db_path)

        if customer.empty:
            # Unknown customer: no history to personalize against, but global
            # popularity is still a valid answer.
            return self._popularity_candidates(None, None, set(), k)

        row = customer.iloc[0]
        history = db.get_customer_purchases(customer_id, self.db_path)
        purchased = set(history["product_id"].astype(str)) if not history.empty else set()

        candidates: dict[str, Recommendation] = {}
        if purchased:
            recent = (
                history.drop_duplicates("product_id")["product_id"]
                .astype(str)
                .head(self.recent_considered)
                .tolist()
            )
            self._merge(candidates, self._association_candidates(recent, purchased))
            self._merge(candidates, self._similarity_candidates(recent, purchased))

        ranked = sorted(candidates.values(), key=lambda r: r.score, reverse=True)[:k]

        if len(ranked) < k:
            already = purchased | {r.product_id for r in ranked}
            ranked.extend(
                self._popularity_candidates(
                    row.get("segment"), row.get("country"), already, k - len(ranked)
                )
            )
        return ranked[:k]

    @staticmethod
    def _merge(target: dict[str, Recommendation], new: list[Recommendation]) -> None:
        """Keep the highest-scoring explanation when two tiers suggest the same
        product, so a product never appears twice in one list."""
        for rec in new:
            existing = target.get(rec.product_id)
            if existing is None or rec.score > existing.score:
                target[rec.product_id] = rec

    def _association_candidates(
        self, recent: list[str], purchased: set[str]
    ) -> list[Recommendation]:
        if self.rules.empty:
            return []

        matched = self.rules[self.rules["antecedent"].astype(str).isin(recent)].copy()
        matched = matched[~matched["consequent"].astype(str).isin(purchased)]
        if matched.empty:
            return []

        # Normalize lift within this candidate set so scores are comparable to
        # cosine similarity, which is already bounded 0-1.
        max_lift = float(matched["lift"].max()) or 1.0
        weight = METHOD_WEIGHTS["association_rule"]

        recs: list[Recommendation] = []
        for _, rule in matched.sort_values("lift", ascending=False).iterrows():
            product_id = str(rule["consequent"])
            recs.append(
                Recommendation(
                    product_id=product_id,
                    product_name=self.name_of(product_id),
                    score=round(weight * float(rule["lift"]) / max_lift, 4),
                    source_method="association_rule",
                    reason_text=(
                        f"Frequently bought with {self.name_of(str(rule['antecedent']))} "
                        f"(confidence {float(rule['confidence']):.0%}, "
                        f"lift {float(rule['lift']):.1f})"
                    ),
                )
            )
        return recs

    def _similarity_candidates(
        self, recent: list[str], purchased: set[str]
    ) -> list[Recommendation]:
        if self.similarity.is_empty:
            return []

        scored = self.similarity.score_against_basket(recent, exclude=purchased, top_n=20)
        weight = METHOD_WEIGHTS["product_similarity"]
        return [
            Recommendation(
                product_id=product_id,
                product_name=self.name_of(product_id),
                score=round(weight * score, 4),
                source_method="product_similarity",
                reason_text=(
                    f"Similar to {self.name_of(source)}, which this customer bought "
                    f"(similarity {score:.2f})"
                ),
            )
            for product_id, score, source in scored
        ]

    def _popularity_candidates(
        self, segment: str | None, country: str | None, exclude: set[str], k: int
    ) -> list[Recommendation]:
        weight = METHOD_WEIGHTS["popularity_fallback"]
        recs: list[Recommendation] = []
        seen = set(exclude)

        # Walk from the narrowest population outward. A tier that returns rows is
        # not necessarily useful — the customer may already own all of them — so
        # keep broadening until K slots are filled or the tiers run out.
        for products in popularity.iter_fallback_tiers(
            segment=segment, country=country, limit=k + len(seen) + 10,
            db_path=self.db_path,
        ):
            max_revenue = float(products["total_revenue"].max()) or 1.0
            population = products["population"].iloc[0]

            for _, product in products.iterrows():
                product_id = str(product["product_id"])
                if product_id in seen:
                    continue
                seen.add(product_id)
                recs.append(
                    Recommendation(
                        product_id=product_id,
                        product_name=self.name_of(product_id),
                        score=round(weight * float(product["total_revenue"]) / max_revenue, 4),
                        source_method="popularity_fallback",
                        reason_text=f"Popular among {population}",
                    )
                )
                if len(recs) >= k:
                    return recs
        return recs


_ENGINE: RecommendationEngine | None = None


def get_engine(db_path: Path | str | None = None, *, refresh: bool = False) -> RecommendationEngine:
    """Return a process-wide engine, building it on first use."""
    global _ENGINE
    if _ENGINE is None or refresh:
        _ENGINE = RecommendationEngine(db_path)
    return _ENGINE


def recommend(
    customer_id: str, k: int = 5, db_path: Path | str | None = None
) -> list[Recommendation]:
    """Public entry point (PRD Section 22)."""
    return get_engine(db_path).recommend(customer_id, k)


def run(db_path: Path | str | None = None) -> pd.DataFrame:
    """Precompute recommendations for every customer and persist them.

    Materializing these keeps dashboard page loads to a single indexed SELECT.
    """
    engine = get_engine(db_path, refresh=True)
    customer_ids = db.get_customer_ids(db_path)

    records: list[dict] = []
    for customer_id in customer_ids:
        for rank, rec in enumerate(engine.recommend(customer_id), start=1):
            records.append(
                {
                    "customer_id": customer_id,
                    "product_id": rec.product_id,
                    "rank": rank,
                    "score": rec.score,
                    "source_method": rec.source_method,
                    "reason_text": rec.reason_text,
                }
            )

    frame = pd.DataFrame(records)
    db.execute("DELETE FROM recommendations", db_path=db_path)
    if not frame.empty:
        db.write_dataframe(frame, "recommendations", db_path=db_path)
        logger.info(
            "Method mix: %s", frame["source_method"].value_counts().to_dict()
        )
    return frame


def load_recommendations(
    customer_id: str, db_path: Path | str | None = None
) -> pd.DataFrame:
    """Read a customer's persisted recommendations."""
    return db.run_query(
        """
        SELECT r.rank, r.product_id, p.product_name, r.score,
               r.source_method, r.reason_text
        FROM recommendations r
        LEFT JOIN products p ON r.product_id = p.product_id
        WHERE r.customer_id = ?
        ORDER BY r.rank
        """,
        (str(customer_id),),
        db_path,
    )
