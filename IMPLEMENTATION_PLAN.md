# RetailPredict — Implementation Plan

This plan operationalizes the PRD's roadmap (Section 29) into concrete, ordered engineering tasks. Each phase lists its objective, tasks, files touched, dependencies, and a definition of done (DoD) matching the PRD's acceptance criteria (Section 30).

---

## Status: Phases 0–10 implemented

Pipeline runs end to end in ~22s on 40K rows; 91 tests pass; all 6 dashboard pages render.

**Deviations from the original plan, and why:**

1. **RFM quintiles are computed on ranks, not raw values.** `pd.qcut` raises on duplicate bin edges, and Frequency is dominated by ties (most customers place one order). Ranking with `method="first"` first is required for the plan's Phase 5 to work at all on real data.
2. **`customers` gained RFM columns** (`recency_days`, `frequency`, `monetary`, `r_score`, `f_score`, `m_score`, `rfm_score`, `segment`, `segment_reason`). The PRD's schema had nowhere to store segmentation output.
3. **Two tables added beyond the PRD's three:** `association_rules` and `recommendations`. Mining Apriori rules takes seconds — running it per dashboard page load would be unusable, so the pipeline materializes both.
4. **`PRAGMA foreign_keys = ON` is issued on every connection.** SQLite disables FK enforcement by default, per connection; without this the schema's `REFERENCES` clauses do nothing and the Phase 3 DoD ("foreign keys valid") is unverifiable.
5. **Phase 1 exploration notebooks were not created.** A synthetic data generator (`scripts/make_sample_data.py`) plus the pipeline's own quality report cover the same ground in reproducible code. Notebooks remain open if wanted for portfolio presentation.
6. **Popularity fallback walks tiers outward instead of taking the first non-empty one.** Found by a test: a customer owning all their segment's top sellers got an empty list, because the tier returned rows that were then all filtered out as already-purchased.
7. **Chart palette validated for colorblind separation** rather than picked by eye; segment colors pinned by name so filtering never repaints surviving series.

**Not yet done:** exploration notebooks (Phase 1), dashboard screenshots for the README, and `git init` + the commit sequence — this directory is not yet a git repository.

---

## Phase 0 — Project Scaffolding
**Objective:** Stand up the repo skeleton so every later phase has a home.

- [ ] Create directory structure per PRD Section 21 (`data/raw`, `data/processed`, `database/`, `notebooks/`, `src/{data,database,analytics,segmentation,recommendations,utils}`, `dashboard/pages/`, `tests/`)
- [ ] `requirements.txt`: pandas, numpy, mlxtend, scikit-learn, streamlit, plotly, pytest, pyyaml
- [ ] `.gitignore`: `database/*.db`, `data/processed/`, `__pycache__/`, `.venv/`
- [ ] `config/column_mapping.yaml` — default UCI column names, override-able
- [ ] `src/utils/config.py` — loads `column_mapping.yaml` + paths
- [ ] `src/utils/logging.py` — shared logger setup
- [ ] `git init` + first commit (`chore: project scaffolding and requirements.txt`)

**Dependencies:** none
**DoD:** `pip install -r requirements.txt` succeeds; folder structure matches Section 21.

---

## Phase 1 — Dataset & Exploration
**Objective:** Understand raw data shape and quality issues before writing pipeline code.

- [ ] Download UCI Online Retail dataset into `data/raw/`
- [ ] `notebooks/01_data_exploration.ipynb`: null rates, dtypes, ranges per column, cancellation rate, negative qty/price counts, duplicate count
- [ ] Write findings as a short markdown section (can live at top of the notebook)

**Dependencies:** Phase 0
**DoD:** Every required column's null rate, dtype, and range documented.

---

## Phase 2 — Data Cleaning Pipeline
**Objective:** Deterministic, scripted cleaning (PRD Sections 8A–8B).

- [ ] `src/data/validate_schema.py` — `validate(df) -> report`: checks required columns exist, flags missing ones, halts with clear message if critical columns absent
- [ ] `src/data/clean_data.py` — `clean(df) -> df`: drop/flag missing `CustomerID` (route to guest pool), dedupe exact rows, exclude cancellations (`InvoiceNo` starts with "C"), filter non-positive qty/price, parse `InvoiceDate` (drop unparseable), fill missing `Description` with `"Unknown Product"`, cast IDs to string
- [ ] `src/data/transform_data.py` — compute `Revenue = Quantity * UnitPrice`, normalize ID formats
- [ ] Data-quality report emitted as `data/processed/quality_report.json` (before/after row counts, % removed by reason)
- [ ] Output cleaned data to `data/processed/clean_transactions.csv`

**Dependencies:** Phase 1
**DoD:** Pipeline runs end-to-end on raw CSV with zero manual steps; quality report generated with concrete numbers.

---

## Phase 3 — SQLite Database
**Objective:** Persist cleaned data relationally (PRD Section 12).

- [ ] `src/database/schema.sql` — `customers`, `products`, `transactions` tables + indexes (per PRD Appendix C)
- [ ] `src/database/load_to_sqlite.py` — reads `clean_transactions.csv`, populates all three tables, materializes `customers.total_orders`/`total_spend` via SQL aggregation
- [ ] `src/database/db.py` — sole DB access module: `get_connection()`, `run_query(sql, params)`, `get_customer(id)`, etc. No other module opens a connection directly.

**Dependencies:** Phase 2
**DoD:** All three tables populated, foreign keys valid, indexes present; sample queries return correct counts against a schema-inspection test.

---

## Phase 4 — SQL Analytics Layer
**Objective:** SQL-driven aggregation (PRD Section 13).

- [ ] `src/analytics/customer_analytics.py` — revenue/orders/last-purchase per customer, repeat-vs-new
- [ ] `src/analytics/product_analytics.py` — best-sellers, revenue by product, co-occurrence pairs (candidate table for market basket)
- [ ] `src/analytics/business_analytics.py` — monthly revenue trend, Pareto check, underperformer detection
- [ ] Each module returns Pandas DataFrames only — no chart/formatting logic
- [ ] `tests/analytics/` — fixture in-memory SQLite DB with known rows, assert against hand-computed values

**Dependencies:** Phase 3
**DoD:** At least 8 distinct SQL analytics queries implemented; each verified against hand-computed values on a fixture DB.

---

## Phase 5 — Customer Segmentation (RFM)
**Objective:** Rule-based RFM segmentation (PRD Section 14).

- [ ] `src/segmentation/rfm.py`:
  - `compute_rfm(df) -> df` — Recency/Frequency/Monetary + quintile scoring via `pd.qcut`
  - `assign_segment(row) -> str` — rule-based mapping (Champions, Loyal, Potential Loyalists, New, At-Risk, Lost, Others)
- [ ] Write segment back to `customers` table (or a `customer_segments` view/column)
- [ ] `notebooks/02_customer_segmentation.ipynb` — validate segment distribution, sanity-check boundary cases
- [ ] `tests/segmentation/test_rfm.py` — quintile calc correctness, boundary-case segment assignment

**Dependencies:** Phase 4
**DoD:** Every customer has a non-null segment; segment counts sanity-checked.

---

## Phase 6 — Recommendation Engine
**Objective:** Hybrid, explainable recommender (PRD Sections 15–16, Appendix D).

- [ ] `src/recommendations/market_basket.py` — build invoice-level baskets, run `mlxtend` Apriori + association_rules (support/confidence/lift), filter confidence ≥ 0.3
- [ ] `src/recommendations/similarity.py` — customer–product interaction matrix, item-item cosine similarity via sklearn
- [ ] `src/recommendations/popularity.py` — top products by segment/country from SQL analytics layer
- [ ] `src/recommendations/engine.py`:
  - `Recommendation` dataclass: `product_id`, `score`, `source_method`, `reason_text`
  - `recommend(customer_id, k=5) -> list[Recommendation]` — merges (a) association rules, (b) similarity, dedupes against purchase history, normalizes/ranks scores, backfills with popularity fallback until K reached
- [ ] `notebooks/03_recommendation_analysis.ipynb` — spot-check recommendations for a few customers
- [ ] `tests/recommendations/` — shape/fields correctness, ranking order, cold-start fallback, no duplicate product IDs

**Dependencies:** Phase 4, Phase 5
**DoD:** `recommend(customer_id, k)` returns K ranked, explained recommendations for both warm and cold-start customers.

---

## Phase 7 — Recommendation Evaluation
**Objective:** Quantify recommender quality (PRD Section 25).

- [ ] `src/recommendations/evaluation.py` — time-based train/test split (hold out each customer's most recent N purchases), compute Precision@K, Recall@K, Hit Rate@K, Coverage
- [ ] Evaluation report (notebook or `data/processed/evaluation_report.json`)
- [ ] Clearly label any business-impact statement as hypothetical/illustrative, never a measured result

**Dependencies:** Phase 6
**DoD:** Metrics computed and documented for the full dataset.

---

## Phase 8 — Streamlit Dashboard
**Objective:** 6-page BI dashboard (PRD Sections 18, Appendix E).

- [ ] `dashboard/app.py` — entry point, shared layout/theme
- [ ] `dashboard/pages/1_Home.py` — KPI cards, revenue trend, top products, segment donut
- [ ] `dashboard/pages/2_Customer_Analytics.py` — search, profile card, purchase history, recommendations panel
- [ ] `dashboard/pages/3_Customer_Segmentation.py` — distribution/contribution charts, RFM heatmap, filters
- [ ] `dashboard/pages/4_Product_Analytics.py` — top products, revenue/quantity charts, co-purchase table
- [ ] `dashboard/pages/5_Recommendation_Center.py` — customer selector, ranked list with reasons, drill-down
- [ ] `dashboard/pages/6_Business_Insights.py` — auto-generated insight cards from live query results
- [ ] All pages import only from `src/` + Plotly/Streamlit — no raw SQL or cleaning logic in `dashboard/`
- [ ] Wrap `db.py` connection logic in try/except; surface Streamlit error banners instead of raw tracebacks

**Dependencies:** Phases 3–7
**DoD:** All 6 pages render correctly against the populated DB with no raw tracebacks.

---

## Phase 9 — Testing
**Objective:** Full pytest suite mirroring `src/`.

- [ ] `tests/data/` — missing-value handling, dedup, revenue calc, invalid-transaction filtering (synthetic fixtures)
- [ ] `tests/database/` — schema-inspection test (tables, FKs, indexes)
- [ ] `tests/analytics/` — already covered in Phase 4, confirm coverage
- [ ] `tests/segmentation/` — already covered in Phase 5, confirm coverage
- [ ] `tests/recommendations/` — already covered in Phases 6–7, confirm coverage
- [ ] `tests/dashboard/` — test only the data-fetch functions dashboard pages call, not Streamlit rendering

**Dependencies:** Phases 2–8
**DoD:** `pytest` passes with meaningful coverage of core logic (not UI).

---

## Phase 10 — Documentation & Portfolio Polish
**Objective:** Portfolio-ready repository (PRD Section 31).

- [ ] `run_pipeline.py` — single orchestration entry point chaining Phases 2–7
- [ ] `README.md` — overview, problem statement, features, architecture diagram, tech stack, dataset description, DB schema, recommendation + segmentation methodology, screenshots, run instructions, example recommendation output, evaluation metrics, future improvements
- [ ] Screenshots of all 6 dashboard pages
- [ ] Clean commit history following the suggested sequence (PRD Section 31)

**Dependencies:** All prior phases
**DoD:** A stranger can clone, follow README, and reproduce the full dashboard in under 15 minutes.

---

## Suggested Commit Sequence
Matches PRD Section 31 — one commit per phase milestone, not one mega-commit:

1. `chore: project scaffolding and requirements.txt`
2. `feat: data validation and cleaning pipeline`
3. `feat: SQLite schema and load script`
4. `feat: SQL analytics layer (customer/product/business queries)`
5. `feat: RFM customer segmentation`
6. `feat: market basket analysis and association rules`
7. `feat: product similarity recommender`
8. `feat: popularity fallback and hybrid recommendation engine`
9. `feat: recommendation evaluation metrics`
10. `feat: Streamlit dashboard (Home, Customer, Segmentation pages)`
11. `feat: Streamlit dashboard (Product, Recommendation, Insights pages)`
12. `test: pytest suite for data/SQL/segmentation/recommendations`
13. `docs: README, architecture diagram, screenshots`

---

## Acceptance Checklist (tracks PRD Section 30)

- [ ] Pipeline runs end-to-end via one command, no manual steps
- [ ] Data-quality report shows concrete before/after numbers
- [ ] SQLite DB has 3 tables, correct FKs, indexes — verified by test
- [ ] ≥8 distinct SQL analytics queries, tested
- [ ] Every customer has an RFM segment
- [ ] Recommendation engine explains recs for warm + cold-start customers
- [ ] Precision@K, Recall@K, Hit Rate@K, Coverage computed and reported
- [ ] All 6 dashboard pages function without errors
- [ ] Pytest suite passes across data, SQL, segmentation, recommendations
- [ ] README enables full reproduction in under 15 minutes
- [ ] No paid APIs, SaaS credentials, or billing-required services anywhere
