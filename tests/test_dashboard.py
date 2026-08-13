"""Dashboard tests.

Per PRD Section 24, only the data-fetch functions the pages rely on are tested,
plus a headless render check that each page executes without raising. Streamlit's
rendering internals are not under test.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from dashboard import theme
from src.utils.config import DATABASE_PATH, PROJECT_ROOT

PAGES = [PROJECT_ROOT / "dashboard" / "app.py"] + sorted(
    (PROJECT_ROOT / "dashboard" / "pages").glob("*.py")
)

needs_database = pytest.mark.skipif(
    not DATABASE_PATH.exists(),
    reason="Run `python run_pipeline.py` to build the database before running these tests.",
)


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
@needs_database
def test_page_renders_without_raising(page: Path):
    app = AppTest.from_file(str(page), default_timeout=180)
    app.run()

    assert not app.exception, (
        f"{page.name} raised: "
        + "; ".join(f"{e.type}: {e.message}" for e in app.exception)
    )


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
@needs_database
def test_page_shows_no_error_banner(page: Path):
    app = AppTest.from_file(str(page), default_timeout=180)
    app.run()

    banners = [e.value for e in app.error]
    assert not banners, f"{page.name} rendered an error banner: {banners}"


# --- Theme helpers -----------------------------------------------------------

def test_every_segment_has_a_pinned_color():
    from src.segmentation import rfm

    for segment in rfm.SEGMENT_REASONS:
        assert segment in theme.SEGMENT_COLORS


def test_every_source_method_has_a_color_and_label():
    from src.recommendations import engine

    for method in engine.METHOD_WEIGHTS:
        assert method in theme.METHOD_COLORS
        assert method in theme.METHOD_LABELS


def test_status_colors_are_not_reused_as_series_colors():
    """A status color must never impersonate a data series."""
    assert not set(theme.STATUS.values()) & set(theme.SERIES)


@pytest.mark.parametrize(
    "value, expected",
    [(1_500_000, "$1.50M"), (2_500, "$2.5K"), (99.5, "$99.50")],
)
def test_currency_formatting(value, expected):
    assert theme.currency(value) == expected
