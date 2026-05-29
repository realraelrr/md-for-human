from __future__ import annotations

from pygments.formatters import HtmlFormatter

from md_for_human.assets import load_asset_text


PYGMENTS_CSS = HtmlFormatter(style="native", cssclass="highlight").get_style_defs(  # type: ignore[no-untyped-call]
    ".article .highlight"
)

BASE_CSS = load_asset_text("base.css").replace("/* MDFH_PYGMENTS_CSS */", PYGMENTS_CSS)
BASE_JS = load_asset_text("base.js")
