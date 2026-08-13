"""Recommendation Center — ranked, explained cross-sell (PRD Appendix E.5)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from dashboard import data, theme  # noqa: E402

st.set_page_config(page_title="Recommendations | RetailPredict", page_icon="🎯", layout="wide")
st.title("Recommendation center")
st.caption(
    "Every recommendation shows the method and the evidence behind it. "
    "Nothing here is a black-box score."
)

ready, message = data.database_is_ready()
if not ready:
    st.error(message)
    st.stop()

ids = data.customer_ids()
if not ids:
    st.warning("No identified customers in the dataset.")
    st.stop()

customer_id = st.selectbox("Select a customer", ids, index=0)
recs = data.recommendations(customer_id)
record = data.customer_record(customer_id)

if not record.empty:
    customer = record.iloc[0]
    segment = customer["segment"] or "Unsegmented"
    st.caption(
        f"Segment: **{segment}**  ·  "
        f"{int(customer['total_orders'] or 0):,} orders  ·  "
        f"{theme.currency(customer['total_spend'] or 0)} lifetime spend"
    )

st.divider()

if recs.empty:
    st.info(
        "Not enough data to generate recommendations for this customer. "
        "This happens when a customer has already purchased every product in the "
        "catalog, or when the dataset is too small to establish patterns."
    )
else:
    left, right = st.columns([3, 2])

    with left:
        st.subheader("Ranked recommendations")
        for _, rec in recs.iterrows():
            method = rec["source_method"]
            color = theme.METHOD_COLORS.get(method, theme.INK_MUTED)
            label = theme.METHOD_LABELS.get(method, method)
            st.markdown(
                f"""<div style="border:1px solid rgba(11,11,11,0.10);border-radius:8px;
                             padding:14px 16px;margin-bottom:12px;background:{theme.SURFACE};">
                  <div style="display:flex;justify-content:space-between;align-items:baseline;">
                    <div>
                      <span style="color:{theme.INK_MUTED};font-size:12px;
                                   font-variant-numeric:tabular-nums;">
                        #{int(rec['rank'])}</span>
                      <strong style="color:{theme.INK_PRIMARY};margin-left:8px;font-size:15px;">
                        {rec['product_name']}</strong>
                    </div>
                    <span style="color:{theme.INK_SECONDARY};font-size:13px;
                                 font-variant-numeric:tabular-nums;">
                      score {rec['score']:.2f}</span>
                  </div>
                  <div style="margin:8px 0 6px;">
                    <span style="display:inline-block;width:8px;height:8px;border-radius:50%;
                                 background:{color};margin-right:6px;"></span>
                    <span style="color:{theme.INK_SECONDARY};font-size:12px;">{label}</span>
                  </div>
                  <div style="color:{theme.INK_SECONDARY};font-size:13px;line-height:1.5;">
                    {rec['reason_text']}</div>
                </div>""",
                unsafe_allow_html=True,
            )

        with st.expander("View as table"):
            st.dataframe(
                recs.rename(
                    columns={
                        "rank": "Rank", "product_name": "Product", "score": "Score",
                        "source_method": "Method", "reason_text": "Reason",
                    }
                )[["Rank", "Product", "Score", "Method", "Reason"]],
                hide_index=True, width="stretch",
            )

    with right:
        st.subheader("How these were generated")
        st.markdown(
            """
The engine works in three tiers and stops once it has enough candidates:

1. **Bought together** — association rules mined with Apriori, ranked by lift.
2. **Similar product** — item-item cosine similarity over purchase history.
3. **Popular pick** — top sellers in the customer's segment, used to fill any
   remaining slots and to cover customers with no history.

Products the customer already bought are always excluded.
"""
        )

        mix = data.recommendation_method_mix()
        if not mix.empty:
            st.subheader("Method mix across all customers")
            mix = mix.copy()
            mix["label"] = mix["source_method"].map(
                lambda m: theme.METHOD_LABELS.get(m, m)
            )
            ordered = mix.sort_values("recommendations")
            fig = go.Figure(
                go.Bar(
                    x=ordered["recommendations"], y=ordered["label"], orientation="h",
                    marker=dict(
                        color=[
                            theme.METHOD_COLORS.get(m, theme.INK_MUTED)
                            for m in ordered["source_method"]
                        ]
                    ),
                    text=[f"{int(v):,}" for v in ordered["recommendations"]],
                    textposition="outside",
                    textfont=dict(color=theme.INK_SECONDARY, size=11),
                    hovertemplate="<b>%{y}</b><br>%{x:,} recommendations<extra></extra>",
                )
            )
            fig.update_xaxes(showticklabels=False, showgrid=False, linecolor="rgba(0,0,0,0)")
            fig.update_yaxes(showgrid=False)
            st.plotly_chart(theme.style(fig, height=220), width="stretch")

st.divider()

# --- Drill-down: the underlying rules ----------------------------------------
st.subheader("Strongest association rules in the dataset")
st.caption(
    "Lift is how much more likely the pairing is than chance. Confidence is the "
    "share of baskets containing product A that also contain product B."
)
rules = data.association_rules(limit=25)

if rules.empty:
    st.info(
        "No association rules were mined. Lower `min_support` in "
        "`config/column_mapping.yaml` and re-run the pipeline."
    )
else:
    st.dataframe(
        rules.rename(
            columns={
                "antecedent_name": "If they buy", "consequent_name": "They also buy",
                "confidence": "Confidence", "lift": "Lift", "support": "Support",
            }
        )[["If they buy", "They also buy", "Confidence", "Lift", "Support"]].round(3),
        hide_index=True, width="stretch", height=380,
    )
