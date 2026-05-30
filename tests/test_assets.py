from __future__ import annotations

from md_for_human.assets import load_asset_text
from md_for_human.review.client_assets import REVIEW_CLIENT_JS, REVIEW_CLIENT_JS_ASSETS


def test_package_assets_load_static_and_review_text() -> None:
    base_css = load_asset_text("base.css")
    base_js = load_asset_text("base.js")
    review_css = load_asset_text("review.css")
    review_js = load_asset_text("review.js")
    review_artifact_js = load_asset_text("review-artifact.js")
    review_source_locator_js = load_asset_text("review-source-locator.js")
    review_comments_renderer_js = load_asset_text("review-comments-renderer.js")

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
    assert 'request("/state")' in review_js
    assert 'document.body.classList.add("mdfh-review-mode");' in review_js
    assert 'bodyLabel.dataset.i18n = "source";' in review_comments_renderer_js
    assert 'commentsLabel.dataset.i18n = "reviewComments";' in review_comments_renderer_js
    assert 'labels.dataset.mdfhUi = "1";' in review_comments_renderer_js
    assert 'window.addEventListener("mdfh:localechange"' in review_js
    assert "window.mdfhReviewArtifact" in review_artifact_js
    assert "window.mdfhReviewSourceLocator" in review_source_locator_js
    assert "window.mdfhReviewCommentsRenderer" in review_comments_renderer_js


def test_review_client_js_is_composed_from_split_assets() -> None:
    assert REVIEW_CLIENT_JS_ASSETS == (
        "review-artifact.js",
        "review-source-locator.js",
        "review-comments-renderer.js",
        "review.js",
    )
    assert REVIEW_CLIENT_JS.index("window.mdfhReviewArtifact") < REVIEW_CLIENT_JS.index(
        "window.mdfhReviewSourceLocator"
    )
    assert REVIEW_CLIENT_JS.index("window.mdfhReviewSourceLocator") < REVIEW_CLIENT_JS.index(
        "window.mdfhReviewCommentsRenderer"
    )
    assert REVIEW_CLIENT_JS.index("window.mdfhReviewCommentsRenderer") < REVIEW_CLIENT_JS.index(
        "__MDFH_TOKEN__"
    )
    assert "ensureV2Artifact" in REVIEW_CLIENT_JS
    assert "firstElementForSourceRange" in REVIEW_CLIENT_JS
    assert "renderInlineComments" in REVIEW_CLIENT_JS
    assert 'request("/state")' in REVIEW_CLIENT_JS
