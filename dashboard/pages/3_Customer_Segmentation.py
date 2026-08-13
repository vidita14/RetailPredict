"""Customer Segmentation — RFM segment sizes, value, and filters
(PRD Appendix E.3)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from dashboard import data, theme  # noqa: E402

st.set_page_config(page_title="Segments | RetailPredict", page_icon="🧩", layout="wide")
st.title("Customer segmentation")
st.caption(
    "Segments are assigned by rule-based RFM scoring: Recency, Frequency, and "
    "Monetary value are each scored 1–5 by quintile, then mapped to a named segment."
)

ready, message = data.database_is_ready()
if not ready:
    st.error(message)
    st.stop()

customers = data.customer_table()
if customers.empty:
    st.warning("No customers to segment.")
    st.stop()

# --- Filters, in one row above the charts ------------------------------------
f1, f2, f3 = st.columns([2, 2, 3])

with f1:
    country_options = ["All countries"] + sorted(customers["country"].dropna().unique().tolist())
    country = st.selectbox("Country", country_options)

with f2:
    segment_options = sorted(customers["segment"].dropna().unique().tolist())
    chosen_segments = st.multiselect(
        "Segment", segment_options, default=segment_options,
        help="Segment colors stay fixed as you filter, so a segment keeps its color.",
    )

with f3:
    max_spend = float(customers["total_spend"].max())
    spend_range = st.slider(
        "Total spend range", 0.0, max_spend, (0.0, max_spend), format="$%.0f"
    )

filtered = customers.copy()
if country != "All countries":
    filtered = filtered[filtered["country"] == country]
if chosen_segments:
    filtered = filtered[filtered["segment"].isin(chosen_segments)]
filtered = filtered[
    filtered["total_spend"].between(spend_range[0], spend_range[1])
]

if filtered.empty:
    st.warning("No customers match these filters.")
    st.stop()

st.caption(f"Showing {len(filtered):,} of {len(customers):,} customers.")

summary = (
    filtered.groupby("segment")
    .agg(
        customers=("customer_id", "count"),
        revenue=("total_spend", "sum"),
        avg_spend=("total_spend", "mean"),
        avg_orders=("total_orders", "mean"),
        avg_recency=("recency_days", "mean"),
    )
    .reset_index()
    .sort_values("revenue", ascending=False)
)

# --- Segment size and value --------------------------------------------------
left, right = st.columns(2)

with left:
    st.subheader("Customers per segment")
    ordered = summary.sort_values("customers")
    fig = go.Figure(
        go.Bar(
            x=ordered["customers"], y=ordered["segment"], orientation="h",
            marker=dict(
                color=[theme.SEGMENT_COLORS.get(s, theme.INK_MUTED) for s in ordered["segment"]]
            ),
            text=[f"{v:,}" for v in ordered["customers"]],
            textposition="outside",
            textfont=dict(color=theme.INK_SECONDARY, size=11),
            hovertemplate="<b>%{y}</b><br>Customers: %{x:,}<extra></extra>",
        )
    )
    fig.update_xaxes(showticklabels=False, showgrid=False, linecolor="rgba(0,0,0,0)")
    fig.update_yaxes(showgrid=False)
    st.plotly_chart(theme.style(fig, height=340), width="stretch")

with right:
    st.subheader("Revenue per segment")
    ordered = summary.sort_values("revenue")
    fig = go.Figure(
        go.Bar(
            x=ordered["revenue"], y=ordered["segment"], orientation="h",
            marker=dict(
                color=[theme.SEGMENT_COLORS.get(s, theme.INK_MUTED) for s in ordered["segment"]]
            ),
            text=[theme.currency(v) for v in ordered["revenue"]],
            textposition="outside",
            textfont=dict(color=theme.INK_SECONDARY, size=11),
            hovertemplate="<b>%{y}</b><br>Revenue: $%{x:,.0f}<extra></extra>",
        )
    )
    fig.update_xaxes(showticklabels=False, showgrid=False, linecolor="rgba(0,0,0,0)")
    fig.update_yaxes(showgrid=False)
    st.plotly_chart(theme.style(fig, height=340), width="stretch")

st.divider()

# --- RFM scatter -------------------------------------------------------------
st.subheader("Recency vs. spend")
st.caption(
    "Each dot is a customer. Ideal customers sit toward the left (bought recently) "
    "and top (spend more). Marker size shows order count."
)

fig = go.Figure()
for segment in summary["segment"]:
    subset = filtered[filtered["segment"] == segment]
    fig.add_trace(
        go.Scatter(
            x=subset["recency_days"], y=subset["total_spend"], mode="markers",
            name=segment,
            marker=dict(
                color=theme.SEGMENT_COLORS.get(segment, theme.INK_MUTED),
                size=(subset["total_orders"].clip(upper=20) * 0.7 + 8),
                line=dict(color=theme.SURFACE, width=1.5),
                opacity=0.8,
            ),
            customdata=subset[["customer_id", "total_orders", "rfm_score"]],
            hovertemplate=(
                "<b>Customer %{customdata[0]}</b><br>Segment: " + segment +
                "<br>Days since last order: %{x:,}<br>Total spend: $%{y:,.0f}"
                "<br>Orders: %{customdata[1]}<br>RFM: %{customdata[2]}<extra></extra>"
            ),
        )
    )
fig.update_xaxes(title="Days since last purchase")
fig.update_yaxes(title="Total spend", tickprefix="$", tickformat="~s", type="log")
st.plotly_chart(theme.style(fig, height=460, showlegend=True), width="stretch")
st.caption("Spend uses a logarithmic scale so the long tail of smaller customers stays readable.")

# --- Segment table -----------------------------------------------------------
st.subheader("Segment detail")
st.dataframe(
    summary.rename(
        columns={
            "segment": "Segment", "customers": "Customers", "revenue": "Revenue",
            "avg_spend": "Avg spend", "avg_orders": "Avg orders",
            "avg_recency": "Avg days since order",
        }
    ).round(1),
    hide_index=True, width="stretch",
)
