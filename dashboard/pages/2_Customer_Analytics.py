"""Customer Analytics — one customer's profile, history, and offers
(PRD Appendix E.2)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from dashboard import data, theme  # noqa: E402

st.set_page_config(page_title="Customers | RetailPredict", page_icon="👤", layout="wide")
st.title("Customer analytics")

ready, message = data.database_is_ready()
if not ready:
    st.error(message)
    st.stop()

ids = data.customer_ids()
if not ids:
    st.warning("No identified customers in the dataset.")
    st.stop()

customer_id = st.selectbox(
    "Select a customer", ids, index=0,
    help="Customers are listed highest-spending first.",
)

record = data.customer_record(customer_id)
if record.empty:
    st.error("Customer not found. Check the ID format and try again.")
    st.stop()

customer = record.iloc[0]
purchases = data.customer_purchases(customer_id)

# --- Profile card ------------------------------------------------------------
st.subheader(f"Customer {customer_id}")

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total spend", theme.currency(customer["total_spend"] or 0))
c2.metric("Orders", theme.count(customer["total_orders"] or 0))
avg_order = (customer["total_spend"] or 0) / max(int(customer["total_orders"] or 1), 1)
c3.metric("Avg order value", theme.currency(avg_order))
c4.metric(
    "Days since last order",
    theme.count(customer["recency_days"]) if customer["recency_days"] is not None else "—",
)
c5.metric("RFM score", customer["rfm_score"] or "—")

segment = customer["segment"] or "Unsegmented"
segment_color = theme.SEGMENT_COLORS.get(segment, theme.INK_MUTED)
st.markdown(
    f"""<div style="display:flex;align-items:center;gap:8px;margin:4px 0 2px;">
      <span style="width:10px;height:10px;border-radius:50%;background:{segment_color};
                   display:inline-block;"></span>
      <strong style="color:{theme.INK_PRIMARY};">{segment}</strong>
      <span style="color:{theme.INK_SECONDARY};">— {customer['segment_reason'] or ''}</span>
    </div>""",
    unsafe_allow_html=True,
)
st.caption(
    f"Country: {customer['country'] or 'Unknown'}  ·  "
    f"First purchase: {str(customer['first_purchase_date'])[:10]}  ·  "
    f"Last purchase: {str(customer['last_purchase_date'])[:10]}"
)

st.divider()

left, right = st.columns([3, 2])

with left:
    st.subheader("Spend over time")
    monthly = data.customer_monthly_spend(customer_id)
    if monthly.empty:
        st.info("No purchase history for this customer.")
    else:
        fig = go.Figure(
            go.Scatter(
                x=monthly["month"], y=monthly["revenue"], mode="lines+markers",
                line=dict(color=theme.PRIMARY, width=2),
                marker=dict(size=8, color=theme.PRIMARY,
                            line=dict(color=theme.SURFACE, width=2)),
                hovertemplate=(
                    "<b>%{x}</b><br>Spend: $%{y:,.2f}"
                    "<br>Orders: %{customdata}<extra></extra>"
                ),
                customdata=monthly["orders"],
            )
        )
        fig.update_layout(hovermode="x unified")
        fig.update_yaxes(tickprefix="$", tickformat="~s")
        st.plotly_chart(theme.style(fig, height=280), width="stretch")

    st.subheader("Purchase history")
    if purchases.empty:
        st.info("No transactions recorded.")
    else:
        display = purchases.copy()
        display["transaction_date"] = display["transaction_date"].str[:10]
        st.dataframe(
            display.rename(
                columns={
                    "invoice_no": "Invoice", "transaction_date": "Date",
                    "product_name": "Product", "quantity": "Qty",
                    "unit_price": "Unit price", "revenue": "Revenue",
                }
            )[["Invoice", "Date", "Product", "Qty", "Unit price", "Revenue"]],
            hide_index=True, width="stretch", height=300,
        )

with right:
    st.subheader("Recommended for this customer")
    recs = data.recommendations(customer_id)

    if recs.empty:
        st.info(
            "Not enough data to generate recommendations for this customer. "
            "This happens when a customer has already purchased everything in "
            "the catalog, or the dataset is too small to find patterns."
        )
    else:
        for _, rec in recs.iterrows():
            method = rec["source_method"]
            color = theme.METHOD_COLORS.get(method, theme.INK_MUTED)
            label = theme.METHOD_LABELS.get(method, method)
            st.markdown(
                f"""<div style="border:1px solid rgba(11,11,11,0.10);border-radius:8px;
                             padding:12px 14px;margin-bottom:10px;background:{theme.SURFACE};">
                  <div style="display:flex;justify-content:space-between;gap:8px;">
                    <strong style="color:{theme.INK_PRIMARY};">{rec['product_name']}</strong>
                    <span style="color:{theme.INK_MUTED};font-variant-numeric:tabular-nums;">
                      {rec['score']:.2f}</span>
                  </div>
                  <div style="margin:6px 0 4px;">
                    <span style="display:inline-block;width:8px;height:8px;border-radius:50%;
                                 background:{color};margin-right:6px;"></span>
                    <span style="color:{theme.INK_SECONDARY};font-size:12px;">{label}</span>
                  </div>
                  <div style="color:{theme.INK_SECONDARY};font-size:13px;">
                    {rec['reason_text']}</div>
                </div>""",
                unsafe_allow_html=True,
            )
