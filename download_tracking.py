"""Erfasst öffentliche Download-Aufrufe und leitet anschließend zum Ziel weiter."""
import html
from urllib.parse import urlparse

import streamlit as st
from firebase_admin import db

from downloads import latest_release, public_link, lurk_link, settings as download_settings
from public_products import load_public_products

EVENTS_PATH = "download_analytics/events"


def _external_https(value):
    value = str(value or "").strip()
    parsed = urlparse(value)
    return value if parsed.scheme == "https" and parsed.netloc and not parsed.username and not parsed.password else ""


def resolve_download(key):
    """Resolve only known product keys; never accept a destination URL from the query string."""
    cfg = download_settings()
    if key == "streamdex":
        target, version = public_link(cfg)
        return _external_https(target), "StreamDex", version
    if key == "lurk":
        target, version = lurk_link(cfg)
        return _external_https(target), "StreamDex Lurk", version
    for product in load_public_products():
        if product.get("key") == key and product.get("status_key") != "coming_soon":
            target = _external_https(product.get("button_url"))
            if target:
                return target, str(product.get("name") or key)[:80], ""
    return "", "", ""


def render_download_redirect(key):
    """Log one click intent, then navigate to the configured HTTPS target."""
    target, name, version = resolve_download(key)
    if not target:
        st.set_page_config(page_title="Download nicht verfügbar", page_icon="📥")
        st.error("Dieser Download ist momentan nicht verfügbar.")
        st.info("Bitte gehe zurück zur StreamDex-Seite oder versuche es später erneut.")
        return
    try:
        db.reference(EVENTS_PATH).push({
            "product_key": str(key)[:80],
            "product_name": name,
            "version": str(version or "")[:40],
            "source": "public_button",
            "ts": {".sv": "timestamp"},
        })
    except Exception:
        # The download must remain usable even if analytics storage is unavailable.
        pass
    st.set_page_config(page_title="Download bereit", page_icon="📥")
    st.success("Der Download-Link wurde erfasst und ist bereit.")
    st.link_button("⬇️ Download jetzt öffnen", target, type="primary", use_container_width=True)
