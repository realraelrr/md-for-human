from __future__ import annotations

from md_for_human.assets import load_asset_text


def test_package_assets_load_static_and_review_text() -> None:
    base_css = load_asset_text("base.css")
    base_js = load_asset_text("base.js")
    review_css = load_asset_text("review.css")
    review_js = load_asset_text("review.js")

    assert ".article" in base_css
    assert ':root[data-theme="dark"]' in base_css
    assert "@media (prefers-color-scheme: dark)" in base_css
    assert "--selection-bg" in base_css
    assert ".theme-toggle" in base_css
    assert ".locale-select" in base_css
    assert "data-sidebar-toggle" in base_js
    assert 'const THEME_STORAGE_KEY = "mdfh-theme";' in base_js
    assert 'const LOCALE_STORAGE_KEY = "mdfh-locale";' in base_js
    assert "zh-CN" in base_js
    assert "zh-TW" in base_js
    assert "window.mdfhI18n" in base_js
    assert "function isUiTranslationElement(element)" in base_js
    assert 'element.closest("[data-mdfh-content=\'1\']")' in base_js
    assert "document.documentElement.lang =" not in base_js
    assert ".mdfh-review-open" in review_css
    assert ".mdfh-review-mode .main-inner" in review_css
    assert "border-left: 1px solid var(--hairline);" in review_css
    assert "var(--review-accent)" in review_css
    assert ".mdfh-review-column-labels" in review_css
    assert ".mdfh-review-comments-label" in review_css
    assert 'request("/state")' in load_asset_text("review.js")
    assert 'document.body.classList.add("mdfh-review-mode");' in review_js
    assert 'bodyLabel.dataset.i18n = "source";' in review_js
    assert 'commentsLabel.dataset.i18n = "reviewComments";' in review_js
    assert 'labels.dataset.mdfhUi = "1";' in review_js
    assert 'window.addEventListener("mdfh:localechange"' in review_js
