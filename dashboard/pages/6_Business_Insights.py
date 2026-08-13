"""Business Insights — auto-generated findings, plus pipeline transparency
(PRD Appendix E.6)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from dashboard import data, theme  # noqa: E402

st.set_page_config(page_title="Insights | RetailPredict", page_icon="💡", layout="wide")
st.title("Business insights")
st.caption(
    "Every sentence below is generated from the currently loaded data — no text is "
    "hardcoded. All figures are historical calculations, not forecasts."
)

ready, message = data.database_is_ready()
if not ready:
    st.error(message)
    st.stop()

TONE_ICONS = {
    "good": "✅", "warning": "⚠️", "serious": "🔶",
    "critical": "🛑", "neutral": "ℹ️",
}

insights = data.business_insights()

for i in range(0, len(insights), 2):
    columns = st.columns(2)
    for column, insight in zip(columns, insights[i : i + 2]):
        color = theme.STATUS.get(insight.tone, theme.INK_MUTED)
        icon = TONE_ICONS.get(insight.tone, "ℹ️")
        metric = (
            f"""<div style="font-size:28px;font-weight:600;color:{theme.INK_PRIMARY};
                        margin:4px 0 8px;">{insight.metric}</div>"""
            if insight.metric else ""
        )
        with column:
            st.markdown(
                f"""<div style="border:1px solid rgba(11,11,11,0.10);border-left:3px solid {color};
                             border-radius:8px;padding:16px 18px;margin-bottom:14px;
                             background:{theme.SURFACE};min-height:190px;">
                  <div style="color:{theme.INK_SECONDARY};font-size:13px;font-weight:600;">
                    {icon} {insight.title}</div>
                  {metric}
                  <div style="color:{theme.INK_SECONDARY};font-size:13px;line-height:1.6;">
                    {insight.body}</div>
                </div>""",
                unsafe_allow_html=True,
            )

st.divider()

# --- Pareto curve ------------------------------------------------------------
st.subheader("Revenue concentration curve")
concentration = data.revenue_concentration()

if concentration.empty:
    st.info("No revenue data available.")
else:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=concentration["cumulative_customer_share"] * 100,
            y=concentration["cumulative_revenue_share"] * 100,
            mode="lines",
            line=dict(color=theme.PRIMARY, width=2),
            name="Actual",
            hovertemplate=(
                "Top %{x:.0f}% of customers<br>generate %{y:.1f}% of revenue<extra></extra>"
            ),
        )
    )
    # Reference line: what perfectly even spend would look like.
    fig.add_trace(
        go.Scatter(
            x=[0, 100], y=[0, 100], mode="lines", name="If spend were equal",
            line=dict(color=theme.AXIS, width=2, dash="dot"),
            hoverinfo="skip",
        )
    )
    fig.update_xaxes(title="Share of customers (%)", ticksuffix="%")
    fig.update_yaxes(title="Share of revenue (%)", ticksuffix="%")
    st.plotly_chart(theme.style(fig, height=380, showlegend=True), width="stretch")

# --- Underperformers ---------------------------------------------------------
st.subheader("Underperforming products")
st.caption("Lowest revenue among products with at least 5 orders, so this is not sampling noise.")
weak = data.underperforming_products(limit=10, min_orders=5)

if weak.empty:
    st.info("No products meet the minimum order threshold.")
else:
    st.dataframe(
        weak.rename(
            columns={
                "product_name": "Product", "total_revenue": "Revenue",
                "units_sold": "Units", "orders": "Orders",
            }
        )[["Product", "Revenue", "Units", "Orders"]].round(2),
        hide_index=True, width="stretch",
    )

st.divider()

# --- Pipeline transparency ---------------------------------------------------
quality_tab, evaluation_tab = st.tabs(["Data quality", "Recommender accuracy"])

with quality_tab:
    report = data.quality_report()
    if report is None:
        st.info("No quality report found. Run `python run_pipeline.py` to generate one.")
    else:
        cleaning = report["cleaning"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Rows read", f"{cleaning['rows_before']:,}")
        c2.metric("Rows kept", f"{cleaning['rows_after']:,}")
        c3.metric("Removed", f"{cleaning['pct_removed']:.2f}%")
        c4.metric("Guest rows kept", f"{cleaning['guest_transaction_rows']:,}")

        st.markdown("**Rows removed, by reason**")
        reasons = cleaning["removed_by_reason"]
        if any(reasons.values()):
            labels = [r.replace("_", " ").capitalize() for r in reasons]
            fig = go.Figure(
                go.Bar(
                    x=list(reasons.values()), y=labels, orientation="h",
                    marker=dict(color=theme.SERIES[1]),
                    text=[f"{v:,}" for v in reasons.values()],
                    textposition="outside",
                    textfont=dict(color=theme.INK_SECONDARY, size=11),
                    hovertemplate="<b>%{y}</b><br>%{x:,} rows removed<extra></extra>",
                )
            )
            fig.update_xaxes(showticklabels=False, showgrid=False, linecolor="rgba(0,0,0,0)")
            fig.update_yaxes(showgrid=False)
            st.plotly_chart(theme.style(fig, height=260), width="stretch")
        else:
            st.success("No rows were removed — the source data was already clean.")

with evaluation_tab:
    report = data.evaluation_report()
    if report is None:
        st.info(
            "No evaluation report found. Run `python run_pipeline.py` "
            "(without `--skip-evaluation`) to generate one."
        )
    else:
        k = report["k"]
        st.caption(
            f"Measured by holding out each customer's most recent invoice, rebuilding "
            f"the recommender on earlier history only, and checking whether the "
            f"held-out products appear in the top {k}. "
            f"Evaluated on {report['customers_evaluated']:,} customers."
        )
        c1, c2, c3, c4 = st.columns(4)
        c1.metric(f"Precision@{k}", f"{report['precision_at_k']:.3f}")
        c2.metric(f"Recall@{k}", f"{report['recall_at_k']:.3f}")
        c3.metric(f"Hit rate@{k}", f"{report['hit_rate_at_k']:.1%}")
        c4.metric("Catalog coverage", f"{report['coverage']:.1%}")

        st.markdown(
            f"""
- **Hit rate** — for {report['hit_rate_at_k']:.1%} of customers, at least one held-out
  purchase appeared in their top {k}.
- **Coverage** — recommendations spanned {report['products_recommended']:,} of
  {report['catalog_size']:,} products, so the engine is not just pushing a handful
  of bestsellers.

These are historical accuracy measurements on this dataset. They are not a
projection of revenue impact.
"""
        )
