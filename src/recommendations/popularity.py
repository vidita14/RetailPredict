"""Popularity fallback (PRD Section 15, tier 3).

Guarantees every customer receives K recommendations, including cold-start
customers with no usable purchase history. Falls back through progressively
broader populations: segment -> country -> global.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pandas as pd

from src.analytics import product_analytics
from src.utils.logging import get_logger

logger = get_logger("recommendations.popularity")


def iter_fallback_tiers(
    segment: str | None = None,
    country: str | None = None,
    limit: int = 20,
    db_path: Path | str | None = None,
) -> Iterator[pd.DataFrame]:
    """Yield candidate product sets from narrowest population to broadest.

    Yielding tiers lazily — rather than returning only the first non-empty one —
    lets the caller keep broadening when a tier's products are all filtered out
    as already-purchased. Otherwise a customer who owns every top seller in their
    own segment would receive nothing, even though the wider catalog still has
    plenty to offer.

    Each frame carries a `population` column naming the group it came from, which
    becomes part of the recommendation's reason text.
    """
    if segment:
        products = product_analytics.get_top_products_by_segment(segment, limit, db_path)
        if not products.empty:
            products = products.copy()
            products["population"] = f"{segment} customers"
            yield products

    if country:
        products = product_analytics.get_top_products_by_country(country, limit, db_path)
        if not products.empty:
            products = products.copy()
            products["population"] = f"customers in {country}"
            yield products

    products = product_analytics.get_global_top_products(limit, db_path)
    if not products.empty:
        products = products.copy()
        products["population"] = "all customers"
        yield products


def get_fallback_products(
    segment: str | None = None,
    country: str | None = None,
    limit: int = 20,
    db_path: Path | str | None = None,
) -> pd.DataFrame:
    """The narrowest non-empty tier — convenience wrapper for callers that do
    not need to broaden past the first result."""
    for products in iter_fallback_tiers(segment, country, limit, db_path):
        return products
    return pd.DataFrame()
