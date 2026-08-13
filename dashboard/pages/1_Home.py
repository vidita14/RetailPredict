"""Home — business overview at a glance (PRD Appendix E.1)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from dashboard import data, theme  # noqa: E402

st.set_page_config(page_title="Home | RetailPredict", page_icon="🏠", layout="wide")
st.title("Business overview")

ready, message = data.database_is_ready()
if not ready:
    st.error(message)
    st.stop()

kpis = data.kpis()

# --- KPI row -----------------------------------------------------------------
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total revenue", theme.currency(kpis["total_revenue"]))
c2.metric("Orders", theme.count(kpis["total_orders"]))
c3.metric("Customers", theme.count(kpis["total_customers"]))
c4.metric("Avg order value", theme.currency(kpis["avg_order_value"]))
c5.metric("Repeat rate", f"{kpis['repeat_rate']:.0%}")
st.caption(
    f"Customers and repeat rate count only identified customers. "
    f"{kpis['guest_rows']:,} transaction lines have no customer ID and are "
    f"included in revenue and product figures only."
)

st.divider()

# --- Revenue trend -----------------------------------------------------------
st.subheader("Revenue over time")
monthly = data.monthly_revenue()

if monthly.empty:
    st.info("No revenue data available.")
else:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=monthly["month"],
            y=monthly["revenue"],
            mode="lines",
            line=dict(color=theme.PRIMARY, width=2),
            fill="tozeroy",
            fillcolor="rgba(42,120,214,0.10)",
            name="Revenue",
            hovertemplate="<b>%{x}</b><br>Revenue: $%{y:,.0f}<extra></extra>",
        )
    )
    # Single series: the title names it, so no legend box is needed.
    fig.update_layout(hovermode="x unified")
    fig.update_yaxes(tickprefix="$", tickformat="~s")
    st.plotly_chart(theme.style(fig, height=320), width="stretch")

# --- Top products and segments ----------------------------------------------
left, right = st.columns(2)

with left:
    st.subheader("Top 10 products by revenue")
    products = data.top_products(limit=10)
    if products.empty:
        st.info("No product data available.")
    else:
        ordered = products.sort_values("total_revenue")
        fig = go.Figure(
            go.Bar(
                x=ordered["total_revenue"],
                y=ordered["product_name"],
                orientation="h",
                marker=dict(color=theme.PRIMARY),
                text=[theme.currency(v) for v in ordered["total_revenue"]],
                textposition="outside",
                textfont=dict(color=theme.INK_SECONDARY, size=11),
                hovertemplate=(
                    "<b>%{y}</b><br>Revenue: $%{x:,.0f}"
                    "<br>Units: %{customdata:,}<extra></extra>"
                ),
                customdata=ordered["units_sold"],
            )
        )
        fig.update_xaxes(showticklabels=False, showgrid=False, linecolor="rgba(0,0,0,0)")
        fig.update_yaxes(showgrid=False, tickfont=dict(size=11))
        st.plotly_chart(theme.style(fig, height=420), width="stretch")

with right:
    st.subheader("Customers by segment")
    segments = data.segment_distribution()
    if segments.empty:
        st.info("No segmentation data. Re-run the pipeline.")
    else:
        colors = [
            theme.SEGMENT_COLORS.get(s, theme.INK_MUTED) for s in segments["segment"]
        ]
        fig = go.Figure(
            go.Pie(
                labels=segments["segment"],
                values=segments["customers"],
                hole=0.55,
                marker=dict(colors=colors, line=dict(color=theme.SURFACE, width=2)),
                # Percentages sit on the slices so identity and magnitude never
                # depend on reading color alone.
                textinfo="percent",
                textfont=dict(size=12, color="#ffffff"),
                sort=False,
                hovertemplate=(
                    "<b>%{label}</b><br>Customers: %{value:,}"
                    "<br>Share: %{percent}<extra></extra>"
                ),
            )
        )
        st.plotly_chart(
            theme.style(fig, height=420, showlegend=True), width="stretch"
        )

        with st.expander("View as table"):
            st.dataframe(
                segments[["segment", "customers", "revenue", "avg_spend"]].rename(
                    columns={
                        "segment": "Segment", "customers": "Customers",
                        "revenue": "Revenue", "avg_spend": "Avg spend",
                    }
                ),
                hide_index=True,
                width="stretch",
            )
