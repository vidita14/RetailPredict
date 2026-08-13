"""Recommendation engine behavior, evaluation metrics, and insight generation."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.analytics import insights
from src.database import db
from src.recommendations import engine as engine_module
from src.recommendations import evaluation, market_basket, similarity
from src.segmentation import rfm


@pytest.fixture
def ready_db(fixture_db):
    """Fixture database with segments and association rules populated."""
    rfm.run(fixture_db)
    market_basket.run(fixture_db)
    return fixture_db


@pytest.fixture
def engine(ready_db):
    return engine_module.RecommendationEngine(ready_db)


def test_recommendations_have_every_explanation_field(engine):
    recs = engine.recommend("C1", k=3)

    assert recs, "expected at least one recommendation"
    for rec in recs:
        assert rec.product_id
        assert rec.product_name
        assert rec.source_method in engine_module.METHOD_WEIGHTS
        assert rec.reason_text.strip(), "every recommendation must carry a reason"
        assert 0.0 <= rec.score <= 1.0


def test_recommendations_are_ranked_by_descending_score(engine):
    scores = [rec.score for rec in engine.recommend("C1", k=5)]
    assert scores == sorted(scores, reverse=True)


def test_no_duplicate_products_in_one_list(engine):
    for customer_id in ("C1", "C2"):
        ids = [rec.product_id for rec in engine.recommend(customer_id, k=5)]
        assert len(ids) == len(set(ids))


def test_already_purchased_products_are_never_recommended(engine, ready_db):
    for customer_id in ("C1", "C2"):
        owned = set(
            db.get_customer_purchases(customer_id, ready_db)["product_id"].astype(str)
        )
        recommended = {rec.product_id for rec in engine.recommend(customer_id, k=5)}
        assert not (recommended & owned)


def test_unknown_customer_falls_back_to_popularity(engine):
    recs = engine.recommend("does-not-exist", k=3)

    assert recs, "an unknown customer must still receive recommendations"
    assert all(rec.source_method == "popularity_fallback" for rec in recs)


def test_cold_start_customer_receives_recommendations(engine):
    """C2 has a single invoice — too little history for reliable association
    rules, so the engine must still return something via a lower tier."""
    recs = engine.recommend("C2", k=3)
    assert recs


def test_recommendation_count_never_exceeds_k(engine):
    assert len(engine.recommend("C1", k=2)) <= 2


def test_shortfall_only_happens_when_the_catalog_is_exhausted(engine, ready_db):
    """Fewer than k recommendations is legitimate only when there are no
    unpurchased products left — never because a tier silently failed."""
    catalog = set(
        db.run_query("SELECT product_id FROM products", db_path=ready_db)["product_id"]
    )
    for customer_id in ("C1", "C2"):
        recs = engine.recommend(customer_id, k=5)
        if len(recs) < 5:
            owned = set(
                db.get_customer_purchases(customer_id, ready_db)["product_id"].astype(str)
            )
            assert len(recs) == len(catalog - owned)


def test_unknown_product_id_does_not_crash_name_lookup(engine):
    assert engine.name_of("NOT-A-PRODUCT") == "NOT-A-PRODUCT"


def test_method_weights_order_the_tiers():
    weights = engine_module.METHOD_WEIGHTS
    assert weights["association_rule"] > weights["product_similarity"]
    assert weights["product_similarity"] > weights["popularity_fallback"]


def test_run_persists_recommendations(ready_db):
    frame = engine_module.run(ready_db)
    stored = db.run_query("SELECT * FROM recommendations", db_path=ready_db)

    assert len(stored) == len(frame)
    assert stored["reason_text"].notna().all()
    assert stored["source_method"].notna().all()


def test_load_recommendations_returns_ranked_rows(ready_db):
    engine_module.run(ready_db)
    stored = engine_module.load_recommendations("C1", ready_db)

    if not stored.empty:
        assert stored["rank"].tolist() == sorted(stored["rank"].tolist())


# --- Similarity --------------------------------------------------------------

def test_similarity_matrix_is_symmetric_with_zero_diagonal(ready_db):
    item_similarity = similarity.build(ready_db)

    if not item_similarity.is_empty:
        assert np.allclose(item_similarity.matrix, item_similarity.matrix.T)
        assert np.allclose(np.diag(item_similarity.matrix), 0.0)


def test_similarity_never_returns_the_seed_product(ready_db):
    item_similarity = similarity.build(ready_db)

    for product_id in item_similarity.product_ids:
        neighbors = [p for p, _ in item_similarity.similar_to(product_id, top_n=10)]
        assert product_id not in neighbors


def test_similarity_handles_an_unknown_product(ready_db):
    assert similarity.build(ready_db).similar_to("NOT-A-PRODUCT") == []


# --- Market basket -----------------------------------------------------------

def test_mined_rules_are_one_to_one(ready_db):
    rules = market_basket.load_rules(ready_db)
    for column in ("antecedent", "consequent"):
        assert rules[column].map(lambda v: isinstance(v, str)).all()


def test_mine_rules_on_empty_baskets_returns_empty_schema():
    rules = market_basket.mine_rules(pd.DataFrame())
    assert rules.empty
    assert list(rules.columns) == ["antecedent", "consequent", "support", "confidence", "lift"]


# --- Evaluation --------------------------------------------------------------

def test_split_holds_out_only_the_most_recent_invoice():
    transactions = pd.DataFrame(
        {
            "invoice_no": ["A", "B", "C", "D"],
            "customer_id": ["C1", "C1", "C1", "C2"],
            "product_id": ["P1", "P2", "P3", "P4"],
            "transaction_date": pd.to_datetime(
                ["2011-01-01", "2011-02-01", "2011-03-01", "2011-01-01"]
            ),
        }
    )
    train, test = evaluation.split_train_test(transactions, holdout_invoices=1, min_invoices=2)

    # C1 has 3 invoices: the newest (C) is held out.
    assert test["C1"] == {"P3"}
    assert "C" not in set(train["invoice_no"])
    # C2 has only one invoice, so it stays entirely in train and is not scored.
    assert "C2" not in test
    assert "D" in set(train["invoice_no"])


def test_metrics_are_within_valid_bounds(ready_db):
    result = evaluation.evaluate(k=3, db_path=ready_db)

    assert 0.0 <= result.precision_at_k <= 1.0
    assert 0.0 <= result.recall_at_k <= 1.0
    assert 0.0 <= result.hit_rate_at_k <= 1.0
    assert 0.0 <= result.coverage <= 1.0


# --- Insights ----------------------------------------------------------------

def test_insights_are_generated_with_live_numbers(ready_db):
    generated = insights.generate(ready_db)

    assert generated
    for insight in generated:
        assert insight.title
        assert insight.body
        assert insight.tone in {"good", "warning", "serious", "critical", "neutral"}


def test_insight_bodies_contain_actual_figures(ready_db):
    """Guards against the text drifting back to hardcoded prose."""
    bodies = " ".join(insight.body for insight in insights.generate(ready_db))
    assert any(character.isdigit() for character in bodies)
