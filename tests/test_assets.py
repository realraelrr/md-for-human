from __future__ import annotations

from md_for_human.assets import load_asset_text


def test_package_assets_load_static_and_review_text() -> None:
    assert ".article" in load_asset_text("base.css")
    assert "data-sidebar-toggle" in load_asset_text("base.js")
    assert ".mdfh-review-open" in load_asset_text("review.css")
    assert 'request("/state")' in load_asset_text("review.js")
