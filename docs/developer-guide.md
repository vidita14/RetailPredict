# Developer Guide

Command-line entry points and the test suite.

[← Back to README](../README.md)

## CLI Reference

RetailPredict has no HTTP API — it is a local pipeline plus a Streamlit dashboard.

| Command | Purpose | Key flags |
|---|---|---|
| `python run_pipeline.py` | Run the full pipeline end to end | `--dataset PATH`, `--db PATH`, `--skip-evaluation` |
| `python scripts/make_sample_data.py` | Generate a synthetic UCI-shaped CSV | `--rows` (default 50000), `--customers` (1200), `--products` (140), `--seed` (42), `--out` |
| `streamlit run dashboard/app.py` | Launch the dashboard | Standard Streamlit flags, e.g. `--server.port` |
| `python -m pytest` | Run the test suite | `-q`, `-k EXPR`, `-x` |

## Testing

```bash
python -m pytest
```

91 tests covering: cleaning correctness against hand-built messy fixtures, SQL aggregations verified against hand-computed values on a fixture database, RFM quintile and boundary-rule behavior (including exhaustive coverage of all 125 score combinations), recommendation invariants (no duplicates, never re-recommends owned products, cold-start fallback), evaluation split correctness, and a headless render check of all six dashboard pages.

Dashboard tests require a built database and skip automatically if one is absent.
