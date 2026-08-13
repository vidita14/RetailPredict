"""Generate a synthetic UCI-Online-Retail-shaped CSV.

Lets the pipeline be exercised end-to-end without the real dataset. The output
deliberately reproduces the messiness described in PRD Section 10: missing
CustomerIDs, cancelled invoices, negative quantities, zero prices, duplicate
rows, and blank descriptions.

Usage:
    python scripts/make_sample_data.py --rows 50000
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from src.utils.config import RAW_DIR

PRODUCT_WORDS = [
    ("WHITE HANGING HEART T-LIGHT HOLDER", 2.55),
    ("REGENCY CAKESTAND 3 TIER", 12.75),
    ("JUMBO BAG RED RETROSPOT", 1.95),
    ("PARTY BUNTING", 4.65),
    ("LUNCH BAG RED RETROSPOT", 1.65),
    ("ASSORTED COLOUR BIRD ORNAMENT", 1.69),
    ("SET OF 3 CAKE TINS PANTRY DESIGN", 4.95),
    ("PACK OF 72 RETROSPOT CAKE CASES", 0.55),
    ("LUNCH BAG BLACK SKULL", 1.65),
    ("NATURAL SLATE HEART CHALKBOARD", 2.95),
    ("HEART OF WICKER SMALL", 1.65),
    ("JAM MAKING SET WITH JARS", 4.25),
    ("RECIPE BOX PANTRY YELLOW DESIGN", 2.95),
    ("SPOTTY BUNTING", 4.95),
    ("ALARM CLOCK BAKELIKE RED", 3.75),
    ("VINTAGE SNAKES & LADDERS", 3.75),
    ("PAPER CHAIN KIT 50'S CHRISTMAS", 2.95),
    ("WOODEN PICTURE FRAME WHITE FINISH", 2.10),
    ("CERAMIC TOP STORAGE JAR", 1.25),
    ("GLASS STAR FROSTED T-LIGHT HOLDER", 2.10),
]

COUNTRIES = [
    ("United Kingdom", 0.82), ("Germany", 0.04), ("France", 0.04),
    ("EIRE", 0.03), ("Spain", 0.02), ("Netherlands", 0.02),
    ("Belgium", 0.015), ("Switzerland", 0.015),
]


def generate(n_rows: int, n_customers: int, n_products: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)

    # Build a product catalog by combining base names with colour variants.
    colours = ["RED", "BLUE", "GREEN", "PINK", "IVORY", "BLACK", "WHITE"]
    catalog = []
    for i in range(n_products):
        base_name, base_price = PRODUCT_WORDS[i % len(PRODUCT_WORDS)]
        colour = colours[(i // len(PRODUCT_WORDS)) % len(colours)]
        name = base_name if i < len(PRODUCT_WORDS) else f"{base_name} {colour}"
        catalog.append(
            {
                "StockCode": f"{22000 + i}",
                "Description": name,
                "UnitPrice": round(float(base_price) * rng.uniform(0.8, 1.3), 2),
            }
        )
    catalog_df = pd.DataFrame(catalog)

    # Zipfian product popularity so a few items dominate — as in real retail.
    popularity = 1.0 / np.arange(1, n_products + 1) ** 0.8
    popularity /= popularity.sum()

    # Customers order at varying rates; a few order very frequently.
    customer_ids = np.arange(12346, 12346 + n_customers)
    customer_weight = rng.pareto(1.5, n_customers) + 1
    customer_weight /= customer_weight.sum()
    customer_country = rng.choice(
        [c for c, _ in COUNTRIES], size=n_customers,
        p=np.array([w for _, w in COUNTRIES]) / sum(w for _, w in COUNTRIES),
    )

    start = datetime(2010, 12, 1, 8, 26)
    span_days = 373

    # Group rows into invoices of 1-15 lines.
    rows: list[dict] = []
    invoice_seq = 536365
    while len(rows) < n_rows:
        basket_size = int(rng.integers(1, 16))
        cust_idx = int(rng.choice(n_customers, p=customer_weight))
        customer = customer_ids[cust_idx]
        country = customer_country[cust_idx]
        when = start + timedelta(
            days=float(rng.uniform(0, span_days)),
            hours=float(rng.uniform(0, 10)),
            minutes=float(rng.integers(0, 60)),
        )
        # Draw a basket without replacement so a product never repeats in one invoice.
        picks = rng.choice(n_products, size=basket_size, replace=False, p=popularity)
        for pick in picks:
            product = catalog_df.iloc[int(pick)]
            rows.append(
                {
                    "InvoiceNo": str(invoice_seq),
                    "StockCode": product["StockCode"],
                    "Description": product["Description"],
                    "Quantity": int(rng.integers(1, 25)),
                    "InvoiceDate": when.strftime("%m/%d/%Y %H:%M"),
                    "UnitPrice": product["UnitPrice"],
                    "CustomerID": str(float(customer)),
                    "Country": country,
                }
            )
        invoice_seq += 1

    df = pd.DataFrame(rows[:n_rows])
    return _inject_messiness(df, rng)


def _inject_messiness(df: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Reproduce the real dataset's data-quality problems."""
    n = len(df)

    # ~25% of rows have no CustomerID (matches the UCI dataset).
    guest_idx = rng.choice(n, size=int(n * 0.25), replace=False)
    df.loc[guest_idx, "CustomerID"] = np.nan

    # ~0.3% blank descriptions.
    blank_idx = rng.choice(n, size=int(n * 0.003), replace=False)
    df.loc[blank_idx, "Description"] = np.nan

    # ~1.5% zero/negative unit prices (data-entry errors).
    price_idx = rng.choice(n, size=int(n * 0.015), replace=False)
    df.loc[price_idx, "UnitPrice"] = 0.0

    # ~1% negative quantities (returns not marked as cancellations).
    qty_idx = rng.choice(n, size=int(n * 0.01), replace=False)
    df.loc[qty_idx, "Quantity"] = -df.loc[qty_idx, "Quantity"].abs()

    # ~2% cancelled invoices, C-prefixed with negative quantities.
    cancel_idx = rng.choice(n, size=int(n * 0.02), replace=False)
    df.loc[cancel_idx, "InvoiceNo"] = "C" + df.loc[cancel_idx, "InvoiceNo"].astype(str)
    df.loc[cancel_idx, "Quantity"] = -df.loc[cancel_idx, "Quantity"].abs()

    # ~1% exact duplicate rows.
    dupe_idx = rng.choice(n, size=int(n * 0.01), replace=False)
    df = pd.concat([df, df.iloc[dupe_idx]], ignore_index=True)

    # A handful of unparseable dates.
    bad_date_idx = rng.choice(len(df), size=25, replace=False)
    df.loc[bad_date_idx, "InvoiceDate"] = "not a date"

    return df.sample(frac=1, random_state=7).reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=50_000)
    parser.add_argument("--customers", type=int, default=1_200)
    parser.add_argument("--products", type=int, default=140)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=str, default=None)
    args = parser.parse_args()

    df = generate(args.rows, args.customers, args.products, args.seed)

    out_path = args.out or (RAW_DIR / "online_retail.csv")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False, encoding="latin-1")
    print(f"Wrote {len(df):,} rows to {out_path}")


if __name__ == "__main__":
    main()
