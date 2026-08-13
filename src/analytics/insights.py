"""Auto-generated business insights (PRD Section 17).

Every sentence is an f-string populated from live query results — never static
text — so the numbers always describe the currently loaded dataset. Where a
figure is a historical calculation rather than a projection, it says so.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.analytics import business_analytics, product_analytics
from src.database import db


@dataclass
class Insight:
    """One rendered insight card."""

    title: str
    body: str
    # "good" | "warning" | "serious" | "critical" | "neutral" — drives the icon
    # and accent color, always paired with a label so status is never color alone.
    tone: str = "neutral"
    metric: str | None = None


def generate(db_path: Path | str | None = None) -> list[Insight]:
    """Build the full insight set for the Business Insights page."""
    insights: list[Insight] = []
    for builder in (
        _revenue_concentration,
        _top_association_rule,
        _at_risk_customers,
        _underperforming_products,
        _repeat_purchase,
        _guest_transactions,
    ):
        insight = builder(db_path)
        if insight is not None:
            insights.append(insight)
    return insights


def _revenue_concentration(db_path: Path | str | None) -> Insight | None:
    """Pareto check computed from the actual cumulative revenue distribution."""
    concentration = business_analytics.get_revenue_concentration(db_path)
    if concentration.empty:
        return None

    top_20 = concentration[concentration["cumulative_customer_share"] <= 0.20]
    if top_20.empty:
        return None

    share = float(top_20["cumulative_revenue_share"].max()) * 100
    customers = len(top_20)

    if share >= 70:
        tone, verdict = "warning", "highly concentrated — losing a few key accounts would hurt"
    elif share >= 50:
        tone, verdict = "neutral", "roughly in line with the classic 80/20 pattern"
    else:
        tone, verdict = "good", "unusually evenly spread across the customer base"

    return Insight(
        title="Revenue concentration",
        metric=f"{share:.0f}%",
        tone=tone,
        body=(
            f"The top 20% of customers ({customers:,} people) generate "
            f"{share:.1f}% of all revenue. That is {verdict}."
        ),
    )


def _top_association_rule(db_path: Path | str | None) -> Insight | None:
    """Surface the strongest cross-sell rule using its real metrics."""
    rules = db.run_query(
        """
        SELECT r.antecedent, r.consequent, r.confidence, r.lift, r.support,
               pa.product_name AS antecedent_name,
               pc.product_name AS consequent_name
        FROM association_rules r
        LEFT JOIN products pa ON r.antecedent = pa.product_id
        LEFT JOIN products pc ON r.consequent = pc.product_id
        ORDER BY r.lift DESC
        LIMIT 1
        """,
        db_path=db_path,
    )
    if rules.empty:
        return Insight(
            title="Cross-sell opportunity",
            tone="neutral",
            body=(
                "No association rules cleared the configured support and confidence "
                "thresholds. Lower `min_support` in config/column_mapping.yaml, or "
                "load a dataset with more multi-item baskets."
            ),
        )

    rule = rules.iloc[0]
    antecedent = rule["antecedent_name"] or rule["antecedent"]
    consequent = rule["consequent_name"] or rule["consequent"]
    lift = float(rule["lift"])

    return Insight(
        title="Strongest cross-sell pairing",
        metric=f"{lift:.1f}x lift",
        tone="good",
        body=(
            f"Customers who buy {antecedent} are {lift:.1f}x more likely than average "
            f"to also buy {consequent} ({float(rule['confidence']):.0%} of such baskets "
            f"contain both). Bundling these two is the clearest promotion candidate."
        ),
    )


def _at_risk_customers(db_path: Path | str | None) -> Insight | None:
    """Live count and recency for the At-Risk segment."""
    at_risk = db.run_query(
        """
        SELECT COUNT(*) AS customers,
               AVG(recency_days) AS avg_recency,
               SUM(total_spend)  AS revenue
        FROM customers WHERE segment = 'At-Risk'
        """,
        db_path=db_path,
    ).iloc[0]

    customers = int(at_risk["customers"] or 0)
    if not customers:
        return None

    total_revenue = float(
        db.run_query("SELECT SUM(total_spend) AS r FROM customers", db_path=db_path)["r"][0] or 1
    )
    revenue_share = 100 * float(at_risk["revenue"] or 0) / total_revenue

    return Insight(
        title="Customers at risk of churning",
        metric=f"{customers:,}",
        tone="serious",
        body=(
            f"{customers:,} customers are flagged At-Risk — they used to buy often and "
            f"spend well, but have not purchased for an average of "
            f"{float(at_risk['avg_recency']):.0f} days. They account for "
            f"{revenue_share:.1f}% of historical revenue, so a retention campaign here "
            f"protects real money."
        ),
    )


def _underperforming_products(db_path: Path | str | None) -> Insight | None:
    """Bottom performers, restricted to products with enough orders to judge."""
    products = business_analytics.get_underperforming_products(
        limit=5, min_orders=5, db_path=db_path
    )
    if products.empty:
        return None

    worst = products.iloc[0]
    return Insight(
        title="Underperforming products",
        metric=f"{len(products)}",
        tone="warning",
        body=(
            f"{len(products)} products have meaningful order volume but the lowest "
            f"revenue in the catalog. The weakest is {worst['product_name']}, with "
            f"{int(worst['units_sold']):,} units across {int(worst['orders']):,} orders "
            f"generating only ${float(worst['total_revenue']):,.0f}. Review pricing or "
            f"delist. Products with fewer than 5 orders are excluded, so this is not "
            f"small-sample noise."
        ),
    )


def _repeat_purchase(db_path: Path | str | None) -> Insight | None:
    kpis = business_analytics.get_kpis(db_path)
    repeat_rate = kpis["repeat_rate"] * 100

    if repeat_rate >= 50:
        tone, verdict = "good", "a strong loyalty base"
    elif repeat_rate >= 25:
        tone, verdict = "neutral", "typical for retail, with room to improve"
    else:
        tone, verdict = "warning", "low — most customers never return"

    return Insight(
        title="Repeat purchase rate",
        metric=f"{repeat_rate:.0f}%",
        tone=tone,
        body=(
            f"{repeat_rate:.1f}% of identified customers have placed more than one order, "
            f"at an average order value of ${kpis['avg_order_value']:,.2f}. That is "
            f"{verdict}."
        ),
    )


def _guest_transactions(db_path: Path | str | None) -> Insight | None:
    """Report the analytics blind spot rather than hiding it (PRD Section 32)."""
    kpis = business_analytics.get_kpis(db_path)
    if not kpis["guest_rows"]:
        return None

    guest_share = 100 * kpis["guest_revenue"] / (kpis["total_revenue"] or 1)
    return Insight(
        title="Transactions without a customer ID",
        metric=f"{guest_share:.0f}%",
        tone="neutral",
        body=(
            f"{kpis['guest_rows']:,} transaction lines carry no customer ID, representing "
            f"${kpis['guest_revenue']:,.0f} ({guest_share:.1f}%) of revenue. These are "
            f"included in product analytics but excluded from every customer-level "
            f"figure on this dashboard, since they cannot be attributed to a person."
        ),
    )
