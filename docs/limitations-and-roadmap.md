# Limitations and Roadmap

[← Back to README](../README.md)

## Known Limitations

- **Shared deployment** — the dashboard reads one shared SQLite database and has no authentication or per-user data isolation. A public demo can use a fixed synthetic snapshot; concurrent pipeline rebuilds and dashboard reads are not coordinated. PostgreSQL becomes relevant if shared writes are required.
- **Evaluation scope** — the split holds out each customer's latest invoice, not one global time period. Synthetic-data metrics have no popularity-baseline comparison and do not demonstrate production accuracy or business impact.
- **Guest transactions** — rows without a customer ID (~25% of the UCI dataset) are kept for product analytics but excluded from every customer-level figure. The dashboard reports this exclusion rather than hiding it.
- **Apriori cost** — rule mining is capped to the top 300 products by invoice frequency; without a cap it is combinatorially expensive on a full catalog.
- **Catalog exhaustion** — a customer who has bought nearly every product receives fewer than K recommendations. This is correct behavior, and the dashboard says so rather than padding the list.

## Future Scope

K-Means segmentation (elbow/silhouette K selection) · PostgreSQL migration · FastAPI REST layer · authentication for shared deployment · cloud deployment · implicit-ALS collaborative filtering · deep-learning recommender baseline · automated retraining · A/B testing framework · real-time event ingestion · multi-store analytics.
