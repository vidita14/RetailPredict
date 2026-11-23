# Methodology

How RetailPredict assigns customer segments, builds recommendations, and measures quality.

[← Back to README](../README.md)

## Customer Segmentation

Rule-based RFM. Each customer is scored 1–5 on three axes:

- **Recency** — days since their last purchase, measured against the day after the dataset's final transaction.
- **Frequency** — distinct invoices.
- **Monetary** — total spend.

Scores are assigned by quintile and combined into a score triple (e.g. `545`), then mapped through a fixed rule table to one of seven named segments: Champions, Loyal Customers, Potential Loyalists, New Customers, At-Risk, Lost, Others.

> **Implementation note.** Quintiles are computed on *ranks*, not raw values. Frequency is dominated by ties — most customers place exactly one order — which gives `pd.qcut` duplicate bin edges and makes it raise on real data. Ranking with `method="first"` breaks ties so the buckets are always well-defined.

Rule-based RFM was chosen over K-Means because it is deterministic, needs no tuning, and every assignment is explainable in one sentence — see [design decisions](design-decisions.md).

## Recommendation Engine

Three explainable tiers, merged into one ranked list:

1. **Association rules** (`mlxtend` Apriori) — SQL builds invoice baskets, mlxtend scores support/confidence/lift. Rules are restricted to one antecedent and one consequent: multi-item rules produce reason text a business user cannot parse.
   → *"Frequently bought with Party Bunting (confidence 46%, lift 1.2)"*
2. **Item-item cosine similarity** (scikit-learn) over a customer×product matrix. A candidate scores by its best similarity to any owned product, so a strong match to one item is not diluted by unrelated purchases.
   → *"Similar to Lunch Bag Red Retrospot, which this customer bought (similarity 0.82)"*
3. **Popularity fallback** — top sellers by segment, then country, then globally. Guarantees cold-start customers get an answer.
   → *"Popular among Champions customers"*

Candidates are merged, deduplicated against purchase history, and ranked by a weighted normalized score (association `1.00` > similarity `0.85` > popularity `0.50`) so tiers order sensibly while ranking *within* each tier stays intact.

The fallback deliberately walks from the narrowest population outward and keeps broadening if a tier's products are all already-owned — otherwise a customer who owns every top seller in their segment would receive an empty list.

### Example output

Sample flow from the bundled 40K-row synthetic dataset:

```text
--- Customer 12789 (Champions) ---
1.000  [Bought together]  PARTY BUNTING
       Frequently bought with LUNCH BAG RED RETROSPOT (confidence 31%, lift 1.2)
0.969  [Bought together]  JUMBO BAG RED RETROSPOT
       Frequently bought with LUNCH BAG RED RETROSPOT (confidence 37%, lift 1.2)
0.699  [Similar product]  ASSORTED COLOUR BIRD ORNAMENT
       Similar to LUNCH BAG RED RETROSPOT, which this customer bought (similarity 0.82)
```

## Evaluation

Each eligible customer's most recent invoice is held out, the recommender is **rebuilt from scratch on the earlier history only**, and we check whether the held-out products surface in the top K. Rebuilding — rather than filtering predictions after the fact — is what makes this a genuine holdout: the rules and similarity matrix never see the test period.

Results on the bundled 40K-row synthetic dataset:

| Metric | Value |
|---|---|
| Precision@5 | 0.186 |
| Recall@5 | 0.161 |
| Hit Rate@5 | 0.604 |
| Coverage | 0.443 |
| Customers evaluated | 819 |
| Catalog size | 140 products |
| Products recommended (union across all customers) | 62 |

Of the recommendations scored during evaluation, association rules produced 1,403 and item similarity produced 2,683 — popularity fallback did not appear in the holdout mix on this dataset.

**Read these honestly.** Hit Rate@5 of 0.604 means that for 60% of customers, at least one held-out purchase appeared in their top 5. Coverage of 0.443 means recommendations spanned 44% of the catalog, so the engine is not merely pushing a handful of bestsellers. These are **historical accuracy measurements on this dataset** — not a projection, and not a claim about revenue impact. Numbers will differ on the real UCI dataset, which has a far larger and sparser catalog.
