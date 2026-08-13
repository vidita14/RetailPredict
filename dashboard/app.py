"""RetailPredict dashboard entry point.

    streamlit run dashboard/app.py

Presentation only: every number on every page comes from `src/`. Streamlit
discovers the pages in `dashboard/pages/` automatically.
"""

from __future__ import annotations

import sys
from pathlib import Path

# The dashboard is launched from the repo root but executed from this file's
# directory, so the project root has to be on sys.path for `src` imports.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st  # noqa: E402

from dashboard.data import database_is_ready  # noqa: E402

st.set_page_config(
    page_title="RetailPredict",
    page_icon="🛒",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("RetailPredict")
st.caption("Customer intelligence and explainable cross-sell for retail transaction data")

ready, message = database_is_ready()
if not ready:
    st.error(message)
    st.stop()

st.markdown(
    """
Use the pages in the sidebar to explore the dataset:

| Page | What it answers |
|---|---|
| **Home** | How is the business doing overall? |
| **Customer Analytics** | Who is this customer and what should I offer them? |
| **Customer Segmentation** | Which groups of customers matter most? |
| **Product Analytics** | What sells, and what sells together? |
| **Recommendation Center** | What should we cross-sell, and why? |
| **Business Insights** | What should I pay attention to right now? |

Every recommendation on this dashboard carries a plain-language reason. Nothing is
shown as a black-box score.
"""
)

st.info(
    "All figures are calculated from the loaded transaction history. "
    "The dashboard does not forecast or estimate future revenue.",
    icon="ℹ️",
)
