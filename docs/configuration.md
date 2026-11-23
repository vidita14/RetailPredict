# Configuration

RetailPredict has no environment variables — every setting lives in [`config/column_mapping.yaml`](../config/column_mapping.yaml), loaded once by `src/utils/config.py` and cached for the process lifetime. All keys below already ship with working defaults in the committed file.

[← Back to README](../README.md)

| Key | Description | Default |
|---|---|---|
| `dataset.path` | Path to the raw CSV, relative to the repo root | `data/raw/online_retail.csv` |
| `dataset.encoding` | CSV text encoding | `latin-1` |
| `columns.*` | Canonical field name → your CSV's actual header (`invoice_no`, `product_id`, `description`, `quantity`, `invoice_date`, `unit_price`, `customer_id`, `country`) | UCI Online Retail headers |
| `cleaning.cancellation_prefix` | Invoice-number prefix that marks a cancellation | `C` |
| `cleaning.unknown_product_name` | Placeholder for missing product descriptions | `Unknown Product` |
| `cleaning.keep_guest_transactions` | Keep rows with no `CustomerID` for product-level analytics | `true` |
| `segmentation.quantiles` | Number of RFM scoring buckets | `5` |
| `recommendations.top_k` | Recommendations returned per customer | `5` |
| `recommendations.min_support` | Apriori minimum support | `0.02` |
| `recommendations.min_confidence` | Apriori minimum confidence | `0.3` |
| `recommendations.min_lift` | Apriori minimum lift | `1.0` |
| `recommendations.max_products_for_apriori` | Cap on products considered for rule mining | `300` |
| `recommendations.min_co_occurrence` | Minimum co-occurrence count for a product pair | `5` |
| `recommendations.max_products_for_similarity` | Cap on the item-item similarity matrix (grows O(n²) in product count) | `1500` |
| `recommendations.recent_products_considered` | Recent purchases used to seed association-rule lookups | `5` |
