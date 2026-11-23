<div align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset=".github/logo-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset=".github/logo-light.svg">
    <img alt="RetailPredict" src=".github/logo-light.svg" width="440">
  </picture>

  <p>Turn a raw retail CSV into explainable customer segments, product recommendations, and a six-page dashboard — all on your laptop.</p>
</div>

<div align="center">

[![License: AGPL v3][license-shield]][license-url]
[![Python 3.11][python-shield]][python-url]
[![Streamlit 1.30+][streamlit-shield]][streamlit-url]
[![91 tests][tests-shield]][tests-url]
[![Local only][local-shield]][local-url]

</div>

<div align="center">
  <a href="#why-retailpredict">Why</a> &middot;
  <a href="#features">Features</a> &middot;
  <a href="#quick-start">Quick Start</a> &middot;
  <a href="#usage">Usage</a> &middot;
  <a href="https://github.com/vidita14/RetailPredict/issues/new?labels=bug">Report Bug</a>
</div>

---

## Why RetailPredict?

RetailPredict helps answer three questions from retail transaction history: which customers are most valuable, which groups may need attention, and which products to cross-sell. It combines rule-based customer segmentation, a hybrid recommendation engine, and a six-page Streamlit dashboard. Every segment and recommendation includes a reason you can inspect. It runs locally without API keys; it does not forecast revenue or measure campaign impact.

## Features

- **Explainable customer segments** — seven named recency/frequency/monetary (RFM) groups, each with a one-sentence reason written by the same rule that assigned it.
- **Recommendations that explain themselves** — every cross-sell names a product and tells you whether it came from a bought-together pattern, a similar item, or segment popularity.
- **Cold-start fallback** — shoppers with no useful purchase history get popularity-based picks. Lists contain up to five products by default, with fewer when the eligible catalog is exhausted.
- **Six-page BI dashboard** — KPIs, customer profiles, segment breakdowns, product analytics, a recommendation center, and auto-generated business insights.
- **Configurable CSV headers** — map your transaction columns to eight required fields in one YAML file, without changing pipeline code.
- **Invoice holdout evaluation** — the recommender is rebuilt without the held-out invoices, then precision, recall, hit rate, and coverage are reported.
- **Data quality surfaced** — cancellations, guest transactions, and unknown products are reported in the dashboard rather than silently dropped.
- **Local-first, zero keys** — one SQLite file, no server, no paid APIs, and no API keys anywhere in the codebase.

## When to Use

| Situation | RetailPredict? |
|---|---|
| Offline analysis of a retail transaction CSV | Yes |
| You need a reason for every segment and recommendation | Yes |
| A local dashboard for a portfolio, a class project, or a small team | Yes |
| Real-time personalization or a shared service with user accounts and data isolation | Not implemented — see [limitations](docs/limitations-and-roadmap.md) |
| A hosted REST API or production streaming pipeline | No — those are future scope |

## Quick Start

```bash
git clone https://github.com/vidita14/RetailPredict.git
cd RetailPredict
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m scripts.make_sample_data --rows 40000 --seed 42
python run_pipeline.py
streamlit run dashboard/app.py
```

Open http://localhost:8501. This generates synthetic data locally; no dataset download is required. Add `--skip-evaluation` to the pipeline command while iterating.

The generator writes `data/raw/online_retail.csv`, and the pipeline rebuilds the configured database. Back up existing data before reusing these paths.

## Install

Python 3.11 or newer. There is no PyPI package; use the source installation in [Quick Start](#quick-start).

## Usage

### Bring your own CSV

Put the file in `data/raw/` and map your headers in `config/column_mapping.yaml`:

```yaml
dataset:
  path: data/raw/my_orders.csv
columns:
  invoice_no: order_id
  product_id: sku
  description: product_name
  quantity: units
  invoice_date: ordered_at
  unit_price: price
  customer_id: buyer_id
  country: country
```

All eight fields are required, although customer IDs and descriptions may contain missing values. Set `dataset.encoding` to match your file, then run `python run_pipeline.py` and launch the dashboard.

### Use the real UCI dataset

Download the [UCI Online Retail dataset](https://archive.ics.uci.edu/dataset/352/online+retail), export its Excel worksheet to `data/raw/online_retail.csv` without changing the headers, and run the pipeline. The default mapping already matches its schema; set `dataset.encoding: utf-8` if you export a UTF-8 CSV. Renaming an Excel file to `.csv` does not convert it.

### Explore in the dashboard

| Page | What it answers |
|---|---|
| Home | How is the business doing overall? — KPIs, revenue trend, top products, segment mix |
| Customer Analytics | Who is this customer and what should I offer them? — profile, history, spend trend, offers |
| Customer Segmentation | Which groups matter most? — segment sizes and value, RFM scatter, filters |
| Product Analytics | What sells, and what sells together? — best sellers, frequently-bought-together pairs |
| Recommendation Center | What should we cross-sell, and why? — ranked picks with reasons and method mix |
| Business Insights | What needs attention now? — auto-generated findings, Pareto curve, quality and accuracy reports |

## Evaluation

Each eligible customer's most recent invoice is held out and the recommender is rebuilt without those invoices. This is a per-customer split, not a global time cutoff: training can include other customers' transactions after a given customer's held-out purchase. Previously purchased products are excluded from recommendations, even when they recur in the held-out basket. On the generated 40K-row synthetic example:

| Metric | Value |
|---|---|
| Precision@5 | 0.186 |
| Recall@5 | 0.161 |
| Hit Rate@5 | 0.604 |
| Coverage | 0.443 |
| Customers evaluated | 819 |

Hit Rate@5 of 0.604 means at least one held-out purchase appeared in the top 5 for 60% of evaluated customers; coverage of 0.443 means recommendations spanned 44% of the 140-product catalog. These synthetic-data results are a pipeline check, not evidence of business impact or improvement over a baseline. Numbers will differ on real UCI data. Your run writes its results to `data/processed/evaluation_report.json`.

[Full evaluation methodology](docs/methodology.md)

---

## Prerequisites

| Requirement | Minimum |
|---|---|
| Python | 3.11 |
| pip | Bundled with Python 3.11 |

## Architecture

Seven pipeline stages turn a CSV into a SQLite database, then six Streamlit pages read it through a single cached data layer. `src/database/db.py` is the only module that opens a connection, so foreign keys and query behavior have one definition.

[Architecture, pipeline flow, and database schema](docs/architecture.md)

## How It Works

Rule-based RFM quintiles produce named segments with a stable reason; a three-tier recommender merges association rules, item-item similarity, and popularity into one ranked list. Read the detailed rules, scoring, and example output.

[Segmentation and recommendation methodology](docs/methodology.md)

## Configuration

Every setting lives in one YAML file — dataset path, column mapping, cleaning rules, RFM buckets, and recommendation thresholds — with working defaults.

[Full configuration reference](docs/configuration.md)

## Design Decisions

Why SQLite over PostgreSQL, rule-based RFM over K-Means, a hybrid recommender over one model, materialized recommendations over live computation, and rank-based quintiles over raw-value cuts.

[Read the rationale](docs/design-decisions.md)

## Development

CLI flags, the test suite, and how the 91 tests are organized.

[Developer guide](docs/developer-guide.md)

## Limitations and Roadmap

The app has no authentication or per-user data isolation. Its dashboard reads a shared SQLite database; concurrent pipeline rebuilds and dashboard use are not coordinated. Guest transactions are excluded from customer-level figures, Apriori is capped to 300 products, and near-complete purchase histories yield fewer than K recommendations.

[Known limitations and future scope](docs/limitations-and-roadmap.md)

## Contributing

1. Fork the repository and create a feature branch: `git checkout -b feat/your-change`.
2. Match the existing style: type hints on all function signatures, `from __future__ import annotations` at the top of every module, and docstrings only where the *why* is not obvious.
3. Add or update tests under `tests/`, using the fixtures in `tests/conftest.py` where they fit.
4. Run the suite: `python -m pytest`.
5. Open a pull request describing the change and why it is needed.

No linter or formatter is configured — keep diffs consistent with the surrounding file.

## License

[GNU AGPL v3](LICENSE).

---

Crafted with [Readme Craft](https://github.com/motiful/readme-craft)

[license-shield]: https://img.shields.io/badge/License-AGPL_v3-blue.svg
[license-url]: LICENSE
[python-shield]: https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white
[python-url]: https://www.python.org/
[streamlit-shield]: https://img.shields.io/badge/Streamlit-1.30%2B-FF4B4B?logo=streamlit&logoColor=white
[streamlit-url]: https://streamlit.io
[tests-shield]: https://img.shields.io/badge/tests-91-0A9EDC?logo=pytest&logoColor=white
[tests-url]: https://github.com/vidita14/RetailPredict/tree/main/tests
[local-shield]: https://img.shields.io/badge/runtime-local%20first-2E7D32
[local-url]: https://github.com/vidita14/RetailPredict
