"""Product Analytics — what sells and what sells together (PRD Appendix E.4)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from dashboard import data, theme  # noqa: E402

st.set_page_config(page_title="Products | RetailPredict", page_icon="📦", layout="wide")
st.title("Product analytics")

ready, message = data.database_is_ready()
if not ready:
    st.error(message)
    st.stop()

country_options = ["All countries"] + data.countries()
country = st.selectbox("Country", country_options)
selected_country = None if country == "All countries" else country

products = data.top_products(limit=15, country=selected_country)
if products.empty:
    st.warning("No product sales for this country.")
    st.stop()

tab_revenue, tab_units, tab_pairs = st.tabs(
    ["Revenue", "Units sold", "Frequently bought together"]
)

with tab_revenue:
    st.subheader("Top 15 products by revenue")
    ordered = products.sort_values("total_revenue")
    fig = go.Figure(
        go.Bar(
            x=ordered["total_revenue"], y=ordered["product_name"], orientation="h",
            marker=dict(color=theme.PRIMARY),
            text=[theme.currency(v) for v in ordered["total_revenue"]],
            textposition="outside",
            textfont=dict(color=theme.INK_SECONDARY, size=11),
            hovertemplate=(
                "<b>%{y}</b><br>Revenue: $%{x:,.0f}"
                "<br>Orders: %{customdata:,}<extra></extra>"
            ),
            customdata=ordered["orders"],
        )
    )
    fig.update_xaxes(showticklabels=False, showgrid=False, linecolor="rgba(0,0,0,0)")
    fig.update_yaxes(showgrid=False, tickfont=dict(size=11))
    st.plotly_chart(theme.style(fig, height=520), width="stretch")

with tab_units:
    st.subheader("Top 15 products by units sold")
    ordered = products.sort_values("units_sold")
    fig = go.Figure(
        go.Bar(
            x=ordered["units_sold"], y=ordered["product_name"], orientation="h",
            # Units is a different measure from revenue, so it gets its own
            # chart rather than a second axis on the revenue chart.
            marker=dict(color=theme.SERIES[2]),
            text=[f"{int(v):,}" for v in ordered["units_sold"]],
            textposition="outside",
            textfont=dict(color=theme.INK_SECONDARY, size=11),
            hovertemplate="<b>%{y}</b><br>Units sold: %{x:,}<extra></extra>",
        )
    )
    fig.update_xaxes(showticklabels=False, showgrid=False, linecolor="rgba(0,0,0,0)")
    fig.update_yaxes(showgrid=False, tickfont=dict(size=11))
    st.plotly_chart(theme.style(fig, height=520), width="stretch")

with tab_pairs:
    st.subheader("Products frequently bought together")
    st.caption(
        "Counts how often two products appear on the same invoice. This is the raw "
        "co-occurrence signal that feeds the market basket analysis."
    )
    min_pairs = st.slider("Minimum times bought together", 2, 50, 5)
    pairs = data.co_occurrence_pairs(min_co_occurrence=min_pairs, limit=50)

    if pairs.empty:
        st.info(
            "No product pairs reach this threshold. Lower the minimum, or load a "
            "dataset with more multi-item invoices."
        )
    else:
        st.dataframe(
            pairs.rename(
                columns={
                    "product_a_name": "Product A", "product_b_name": "Product B",
                    "co_occurrence": "Bought together",
                }
            )[["Product A", "Product B", "Bought together"]],
            hide_index=True, width="stretch", height=420,
        )

st.divider()

st.subheader("Full product catalog")
performance = data.product_performance()
st.dataframe(
    performance.rename(
        columns={
            "product_id": "ID", "product_name": "Product", "units_sold": "Units",
            "total_revenue": "Revenue", "orders": "Orders", "customers": "Customers",
            "avg_unit_price": "Avg price",
        }
    )[["ID", "Product", "Units", "Revenue", "Orders", "Customers", "Avg price"]].round(2),
    hide_index=True, width="stretch", height=340,
)
