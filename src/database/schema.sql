-- RetailPredict schema (PRD Section 12 / Appendix C).
-- Line-item grain: one `transactions` row = one product line within one invoice.

DROP TABLE IF EXISTS recommendations;
DROP TABLE IF EXISTS association_rules;
DROP TABLE IF EXISTS transactions;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS customers;

CREATE TABLE customers (
    customer_id         TEXT PRIMARY KEY,
    country             TEXT,
    first_purchase_date DATE,
    last_purchase_date  DATE,
    total_orders        INTEGER DEFAULT 0,
    total_spend         REAL    DEFAULT 0,
    -- RFM segmentation output (populated by src/segmentation/rfm.py).
    recency_days        INTEGER,
    frequency           INTEGER,
    monetary            REAL,
    r_score             INTEGER,
    f_score             INTEGER,
    m_score             INTEGER,
    rfm_score           TEXT,
    segment             TEXT,
    segment_reason      TEXT
);

CREATE TABLE products (
    product_id   TEXT PRIMARY KEY,
    product_name TEXT,
    category     TEXT
);

CREATE TABLE transactions (
    transaction_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_no       TEXT NOT NULL,
    -- NULL for guest transactions (no CustomerID in the source row). These rows
    -- count toward product analytics but are excluded from customer analytics.
    customer_id      TEXT REFERENCES customers(customer_id),
    product_id       TEXT REFERENCES products(product_id),
    transaction_date DATETIME NOT NULL,
    quantity         INTEGER CHECK (quantity > 0),
    unit_price       REAL    CHECK (unit_price > 0),
    revenue          REAL,
    country          TEXT
);

-- Association rules mined by mlxtend, persisted so the dashboard never re-runs
-- Apriori at page-render time.
CREATE TABLE association_rules (
    rule_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    antecedent  TEXT NOT NULL,
    consequent  TEXT NOT NULL,
    support     REAL,
    confidence  REAL,
    lift        REAL
);

-- Precomputed per-customer recommendations with their explanations.
CREATE TABLE recommendations (
    recommendation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id       TEXT REFERENCES customers(customer_id),
    product_id        TEXT REFERENCES products(product_id),
    rank              INTEGER,
    score             REAL,
    source_method     TEXT,
    reason_text       TEXT
);

CREATE INDEX idx_transactions_customer ON transactions(customer_id);
CREATE INDEX idx_transactions_product  ON transactions(product_id);
CREATE INDEX idx_transactions_date     ON transactions(transaction_date);
CREATE INDEX idx_transactions_invoice  ON transactions(invoice_no);

CREATE INDEX idx_customers_segment     ON customers(segment);
CREATE INDEX idx_rules_antecedent      ON association_rules(antecedent);
CREATE INDEX idx_recommendations_customer ON recommendations(customer_id);
