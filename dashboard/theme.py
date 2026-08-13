"""Shared chart palette and Plotly styling.

The categorical palette is validated for colorblind separation against the light
chart surface (#fcfcfb): worst adjacent CVD dE 9.1, worst normal-vision dE 19.6.
Three slots sit below 3:1 contrast on this surface, so every chart using them
also ships direct labels or an accompanying table — never color alone.

Presentation only. No queries or business logic live here.
"""

from __future__ import annotations

import plotly.graph_objects as go

# --- Surfaces and ink --------------------------------------------------------
SURFACE = "#fcfcfb"
PAGE = "#f9f9f7"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
AXIS = "#c3c2b7"

# --- Categorical slots, in fixed order (light mode) --------------------------
SERIES = [
    "#2a78d6",  # 1 blue
    "#eb6834",  # 2 orange
    "#1baf7a",  # 3 aqua
    "#eda100",  # 4 yellow
    "#e87ba4",  # 5 magenta
    "#008300",  # 6 green
    "#4a3aa7",  # 7 violet
    "#e34948",  # 8 red
]
PRIMARY = SERIES[0]

# --- Sequential blue ramp (magnitude encoding) -------------------------------
SEQUENTIAL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#2a78d6", "#1c5cab", "#104281"]

# --- Status colors (reserved; never reused as a series) ----------------------
STATUS = {
    "good": "#0ca30c",
    "warning": "#fab219",
    "serious": "#ec835a",
    "critical": "#d03b3b",
}

# Segment colors are pinned by name so a filtered chart never repaints the
# survivors — color follows the entity, not its rank in the current view.
SEGMENT_COLORS = {
    "Champions": SERIES[0],
    "Loyal Customers": SERIES[2],
    "Potential Loyalists": SERIES[1],
    "New Customers": SERIES[3],
    "At-Risk": SERIES[4],
    "Lost": SERIES[7],
    "Others": SERIES[6],
    "Unsegmented": INK_MUTED,
}

# Recommendation source methods also get stable colors.
METHOD_COLORS = {
    "association_rule": SERIES[0],
    "product_similarity": SERIES[2],
    "popularity_fallback": SERIES[3],
}

METHOD_LABELS = {
    "association_rule": "Bought together",
    "product_similarity": "Similar product",
    "popularity_fallback": "Popular pick",
}


def style(fig: go.Figure, *, height: int = 360, showlegend: bool = False) -> go.Figure:
    """Apply the shared chart chrome: recessive axes, no chart junk."""
    fig.update_layout(
        height=height,
        showlegend=showlegend,
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font=dict(
            family='system-ui, -apple-system, "Segoe UI", sans-serif',
            size=13,
            color=INK_SECONDARY,
        ),
        margin=dict(l=8, r=8, t=32, b=8),
        hoverlabel=dict(
            bgcolor=SURFACE,
            bordercolor=AXIS,
            font=dict(color=INK_PRIMARY, size=12),
        ),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
            font=dict(color=INK_SECONDARY, size=12),
        ),
    )
    fig.update_xaxes(
        showgrid=False,
        linecolor=AXIS,
        tickcolor=AXIS,
        tickfont=dict(color=INK_MUTED, size=12),
        title_font=dict(color=INK_MUTED, size=12),
    )
    fig.update_yaxes(
        showgrid=True,
        gridcolor=GRIDLINE,
        gridwidth=1,
        zeroline=False,
        linecolor="rgba(0,0,0,0)",
        tickfont=dict(color=INK_MUTED, size=12),
        title_font=dict(color=INK_MUTED, size=12),
    )
    return fig


def currency(value: float) -> str:
    """Compact money formatting for KPI tiles and labels."""
    value = float(value)
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    if abs(value) >= 1_000:
        return f"${value / 1_000:.1f}K"
    return f"${value:,.2f}"


def count(value: float) -> str:
    return f"{int(value):,}"
