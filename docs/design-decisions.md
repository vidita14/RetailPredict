# Design Decisions

The tradeoffs behind RetailPredict's architecture and algorithms.

[← Back to README](../README.md)

## Why SQLite instead of PostgreSQL?

1. Single-user, local-first tool — no server process to install, configure, or keep running.
2. Ships in the Python standard library (`sqlite3`) — zero extra dependencies.
3. The whole database is one file (`database/retailpredict.db`); resetting state is deleting a file and re-running the pipeline.
4. A fixed snapshot can serve multiple dashboard viewers; PostgreSQL is an upgrade path when concurrent writes are needed. Authentication and data isolation are separate concerns — see [limitations](limitations-and-roadmap.md).

## Why rule-based RFM instead of K-Means?

1. Deterministic — the same input always produces the same segment, with no random initialization to seed or reproduce.
2. Needs no tuning — no cluster count to choose, no elbow/silhouette analysis.
3. Every assignment is explainable in one sentence (`segment_reason`), because the rule that assigned it *is* the explanation — a cluster centroid distance is not.
4. K-Means on scaled RFM features is documented as the natural v2 once the project needs to demonstrate unsupervised methods too.

## Why a three-tier hybrid recommender instead of one model?

1. The project's core constraint is that every recommendation ships a plain-language reason — a single collaborative-filtering or deep model produces a score, not a reason.
2. Association rules, item similarity, and popularity each fail differently: rules need co-occurrence, similarity needs an owned item to compare against, popularity needs nothing. The fallback fills remaining slots for cold-start customers when eligible products exist; an exhausted catalog can yield fewer than K picks.
3. Tier weighting (association `1.00` > similarity `0.85` > popularity `0.50`) lets stronger evidence outrank weaker evidence between tiers while preserving each tier's internal ranking.

## Why materialize rules and recommendations instead of computing them live?

1. Apriori rule mining takes seconds even capped to 300 products — re-running it on every Streamlit widget interaction would make the dashboard unusable.
2. Materializing turns every dashboard read into a single indexed `SELECT`, keeping page loads fast regardless of catalog size.
3. The tradeoff is explicit: recommendations reflect the data as of the last `python run_pipeline.py` run, not live. `dashboard/data.py` caches with a 10-minute TTL so a mid-session pipeline re-run is eventually picked up without an app restart.

## Why rank-based RFM quintiles instead of raw-value quintiles?

1. `pd.qcut` on raw values raises on duplicate bin edges, and Frequency is dominated by ties — most customers place exactly one order.
2. Ranking with `method="first"` breaks ties deterministically, so quintile buckets are always well-defined on real, skewed retail data.
3. This was a deviation from the original implementation plan, discovered when Phase 5 (segmentation) failed on real data — see `IMPLEMENTATION_PLAN.md`.
