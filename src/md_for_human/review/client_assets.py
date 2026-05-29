from __future__ import annotations

import html
import json

from md_for_human.assets import load_asset_text
from md_for_human.review.constants import REVIEW_API_PREFIX
from md_for_human.static_assets import BASE_CSS, BASE_JS


def inject_review_client(html_text: str, token: str, *, nonce: str) -> str:
    html_text = add_owned_asset_nonce(html_text, nonce)
    markup = review_client_markup(token, nonce=nonce)
    if "</body>" in html_text:
        return html_text.replace("</body>", f"{markup}\n</body>", 1)
    return html_text + markup


def add_owned_asset_nonce(html_text: str, nonce: str) -> str:
    escaped_nonce = html.escape(nonce, quote=True)
    html_text = replace_first(
        html_text,
        f"<style data-mdfh-base-style>{BASE_CSS}</style>",
        f'<style data-mdfh-base-style nonce="{escaped_nonce}">{BASE_CSS}</style>',
    )
    html_text = replace_first(
        html_text,
        f"<style>{BASE_CSS}</style>",
        f'<style nonce="{escaped_nonce}">{BASE_CSS}</style>',
    )
    html_text = replace_last(
        html_text,
        f"<script data-mdfh-base-script>{BASE_JS}</script>",
        f'<script data-mdfh-base-script nonce="{escaped_nonce}">{BASE_JS}</script>',
    )
    return replace_last(
        html_text,
        f"<script>{BASE_JS}</script>",
        f'<script nonce="{escaped_nonce}">{BASE_JS}</script>',
    )


def replace_first(value: str, old: str, new: str) -> str:
    return value.replace(old, new, 1)


def replace_last(value: str, old: str, new: str) -> str:
    head, found, tail = value.rpartition(old)
    if not found:
        return value
    return f"{head}{new}{tail}"


def review_client_markup(token: str, *, nonce: str) -> str:
    escaped_nonce = html.escape(nonce, quote=True)
    script = REVIEW_CLIENT_JS.replace("__MDFH_TOKEN__", json.dumps(token)).replace(
        "__MDFH_API_PREFIX__",
        json.dumps(REVIEW_API_PREFIX),
    )
    return (
        f'<style data-mdfh-review-style nonce="{escaped_nonce}">{REVIEW_CLIENT_CSS}</style>'
        f"\n{REVIEW_CLIENT_PANEL}\n"
        f'<script data-mdfh-review-script nonce="{escaped_nonce}">{script}</script>'
    )


REVIEW_CLIENT_CSS = load_asset_text("review.css")
REVIEW_CLIENT_PANEL = """
<button type="button" class="mdfh-review-open" data-mdfh-review-open data-mdfh-ui="1" data-i18n="reviewComment">Comment</button>
<div class="mdfh-review-unplaced" data-mdfh-review-unplaced hidden></div>
<div class="mdfh-review-toast" data-mdfh-review-toast role="status" hidden></div>
""".strip()
REVIEW_CLIENT_JS = load_asset_text("review.js")
