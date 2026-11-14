"""Öffentliches StreamDex-Produktportfolio und Admin-Editor."""
import html
import re
from urllib.parse import urlparse

import streamlit as st
from firebase_admin import db


DEFAULT_PRODUCTS = [
    {
        "key": "streamdex",
        "name": "StreamDex",
        "eyebrow": "CREATOR PLATFORM",
        "description": "Dein zentraler Ort für Streamer-Tools, Community, Planung und Interaktion.",
        "status": "Verfügbar",
        "status_key": "available",
        "icon": "⚡",
        "button_label": "StreamDex entdecken",
        "button_url": "/?dashboard=1",
        "visible": True,
        "accent": "violet",
    },
    {
        "key": "mod_control",
        "name": "StreamDex Mod Control",
        "eyebrow": "MODERATION DESKTOP APP",
        "description": "Behalte Moderation, Team und wichtige Aktionen deines Twitch-Kanals im Blick.",
        "status": "Verfügbar",
        "status_key": "available",
        "icon": "🛡️",
        "button_label": "Download starten",
        "button_url": "",
        "visible": True,
        "accent": "cyan",
    },
    {
        "key": "arcaid",
        "name": "StreamDex Arcaid",
        "eyebrow": "COMING SOON",
        "description": "Ein neuer Bereich im StreamDex-Universum. Weitere Informationen folgen bald.",
        "status": "Coming Soon",
        "status_key": "coming_soon",
        "icon": "🗃️",
        "button_label": "Demnächst verfügbar",
        "button_url": "",
        "visible": True,
        "accent": "amber",
    },
]
PRODUCTS_PATH = "public_product_catalog"


def _safe_url(value):
    value = str(value or "").strip()
    if not value:
        return ""
    if value.startswith("/") and not value.startswith("//"):
        return value
    parsed = urlparse(value)
    return value if parsed.scheme in ("https", "http") and parsed.netloc else ""


def load_public_products():
    """Load editable product content; defaults keep the page usable before first save."""
    try:
        stored = db.reference(PRODUCTS_PATH).get()
    except Exception:
        stored = None
    stored = stored if isinstance(stored, dict) else {}
    products = []
    for default in DEFAULT_PRODUCTS:
        item = dict(default)
        saved = stored.get(default["key"])
        if isinstance(saved, dict):
            for field in ("name", "eyebrow", "description", "status", "status_key",
                          "icon", "button_label", "button_url", "visible", "accent"):
                if field in saved:
                    item[field] = saved[field]
        item["button_url"] = _safe_url(item.get("button_url"))
        item["visible"] = bool(item.get("visible", True))
        products.append(item)
    return products


def _product_card(product, index):
    name = html.escape(str(product.get("name") or "StreamDex"))
    eyebrow = html.escape(str(product.get("eyebrow") or "STREAMDEX"))
    description = html.escape(str(product.get("description") or ""))
    icon = html.escape(str(product.get("icon") or "✦"))
    status = html.escape(str(product.get("status") or "Verfügbar"))
    status_key = str(product.get("status_key") or "available")
    accent = str(product.get("accent") or "violet")
    accent = accent if accent in ("violet", "cyan", "amber") else "violet"
    url = _safe_url(product.get("button_url"))
    label = html.escape(str(product.get("button_label") or "Mehr erfahren"))
    coming = status_key == "coming_soon"
    action = (
        f'<span class="sd-product-soon">{label}</span>' if coming or not url
        else f'<a class="sd-product-action" href="{html.escape(url, quote=True)}">{label} <span>↗</span></a>'
    )
    return (
        f'<article class="sd-product-card accent-{accent}">'
        f'<div class="sd-product-top"><span class="sd-product-icon">{icon}</span>'
        f'<span class="sd-product-status {"soon" if coming else "ready"}">{status}</span></div>'
        f'<div class="sd-product-eyebrow">{eyebrow}</div>'
        f'<h3>{name}</h3><p>{description}</p>'
        f'<div class="sd-product-bottom">{action}</div></article>'
    )


def render_public_product_portfolio():
    products = [p for p in load_public_products() if p.get("visible")]
    cards = "".join(_product_card(p, i) for i, p in enumerate(products))
    st.markdown(
        """
        <style>
        .sd-products-section{margin:42px 0 34px;padding:clamp(18px,3vw,30px);border:1px solid rgba(120,105,190,.22);
          border-radius:22px;background:linear-gradient(145deg,rgba(16,22,46,.78),rgba(8,14,30,.88));
          box-shadow:0 20px 55px rgba(0,0,0,.18)}
        .sd-products-heading{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;margin-bottom:20px}
        .sd-products-kicker{font:800 .65rem 'JetBrains Mono',monospace;letter-spacing:.15em;color:#a78bfa;margin-bottom:7px}
        .sd-products-heading h2{margin:0 0 5px!important;color:#f7f7ff;font-size:clamp(1.35rem,2.4vw,1.85rem)!important;letter-spacing:-.04em}
        .sd-products-heading p{margin:0;color:#9ba8c8;font-size:.83rem;line-height:1.6}
        .sd-products-count{flex:0 0 auto;padding:7px 11px;border:1px solid rgba(167,139,250,.24);border-radius:99px;
          background:rgba(109,40,217,.1);color:#c4b5fd;font-size:.68rem;font-weight:800}
        .sd-product-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}
        .sd-product-card{position:relative;display:flex;flex-direction:column;min-width:0;min-height:235px;padding:19px;
          border:1px solid rgba(148,163,184,.16);border-radius:17px;overflow:hidden;
          background:linear-gradient(155deg,rgba(19,28,54,.96),rgba(10,16,34,.98));
          box-shadow:0 12px 30px rgba(0,0,0,.16);transition:transform .18s,border-color .18s,box-shadow .18s}
        .sd-product-card:before{content:"";position:absolute;right:-65px;top:-85px;width:190px;height:190px;border-radius:50%;
          background:radial-gradient(circle,var(--product-glow),transparent 70%);pointer-events:none}
        .sd-product-card:hover{transform:translateY(-3px);border-color:rgba(167,139,250,.46);box-shadow:0 18px 38px rgba(0,0,0,.25)}
        .sd-product-card.accent-violet{--product-glow:rgba(139,92,246,.22)}
        .sd-product-card.accent-cyan{--product-glow:rgba(34,211,238,.18)}
        .sd-product-card.accent-amber{--product-glow:rgba(245,158,11,.16)}
        .sd-product-top{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:20px;position:relative}
        .sd-product-icon{display:grid;place-items:center;width:47px;height:47px;border:1px solid rgba(167,139,250,.24);
          border-radius:14px;background:linear-gradient(135deg,rgba(139,92,246,.2),rgba(34,211,238,.08));font-size:1.45rem}
        .sd-product-status{padding:6px 9px;border-radius:99px;font-size:.63rem;font-weight:850;white-space:nowrap}
        .sd-product-status.ready{color:#86efac;border:1px solid rgba(34,197,94,.24);background:rgba(22,101,52,.16)}
        .sd-product-status.soon{color:#fcd34d;border:1px solid rgba(245,158,11,.25);background:rgba(120,53,15,.17)}
        .sd-product-eyebrow{position:relative;color:#a78bfa;font:800 .59rem 'JetBrains Mono',monospace;letter-spacing:.13em;margin-bottom:6px}
        .sd-product-card h3{position:relative;margin:0 0 8px!important;color:#f8fafc;font-size:1.08rem!important;letter-spacing:-.025em}
        .sd-product-card p{position:relative;color:#9eabc8;font-size:.78rem;line-height:1.65;margin:0 0 20px}
        .sd-product-bottom{position:relative;margin-top:auto;padding-top:12px;border-top:1px solid rgba(148,163,184,.12)}
        .sd-product-action{display:flex;align-items:center;justify-content:space-between;color:#e9ddff!important;text-decoration:none!important;
          font-size:.75rem;font-weight:850;padding:9px 11px;border:1px solid rgba(167,139,250,.34);border-radius:10px;
          background:linear-gradient(100deg,rgba(124,58,237,.24),rgba(8,127,156,.12))}
        .sd-product-action:hover{border-color:rgba(196,181,253,.7);background:rgba(124,58,237,.3)}
        .sd-product-soon{display:block;color:#8b96b3;font-size:.73rem;font-weight:750;padding:9px 2px}
        @media(max-width:850px){.sd-product-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
        @media(max-width:580px){.sd-products-heading{align-items:flex-start;flex-direction:column}.sd-product-grid{grid-template-columns:1fr}.sd-product-card{min-height:205px}}
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        '<section class="sd-products-section" id="tools">'
        '<div class="sd-products-heading"><div><div class="sd-products-kicker">DAS STREAMDEX UNIVERSUM</div>'
        '<h2>Ein Ökosystem. Deine Tools.</h2>'
        '<p>Entdecke die verfügbaren StreamDex-Produkte und kommende Erweiterungen.</p></div>'
        f'<span class="sd-products-count">{len(products)} PRODUKTE</span></div>'
        f'<div class="sd-product-grid">{cards}</div></section>',
        unsafe_allow_html=True,
    )


def render_admin_product_editor():
    st.markdown("## 🧩 Öffentliche Produktseite")
    st.caption("Hier steuerst du, welche Produkte auf der Dashboard-Startseite erscheinen und wohin die jeweiligen Buttons führen.")
    products = load_public_products()
    st.info("Änderungen werden in Firebase unter public_product_catalog gespeichert. Download-Links werden erst öffentlich verwendet, wenn du sie hier einträgst und speicherst.")
    labels = {p["key"]: p["name"] for p in products}
    selected = st.selectbox("Produkt bearbeiten", list(labels), format_func=lambda key: labels[key], key="public_product_selected")
    product = next(p for p in products if p["key"] == selected)
    with st.form(f"public_product_form_{selected}"):
        c1, c2 = st.columns([2, 1])
        with c1:
            name = st.text_input("Produktname", value=str(product["name"]))
            eyebrow = st.text_input("Kleine Überschrift", value=str(product["eyebrow"]))
        with c2:
            icon = st.text_input("Icon / Emoji", value=str(product["icon"]), max_chars=8)
            accent = st.selectbox("Akzentfarbe", ["violet", "cyan", "amber"], index=["violet", "cyan", "amber"].index(product["accent"]))
        description = st.text_area("Beschreibung", value=str(product["description"]), height=100)
        c3, c4 = st.columns(2)
        with c3:
            status_key = st.selectbox("Produktstatus", ["available", "coming_soon"], index=0 if product["status_key"] == "available" else 1)
            status = st.text_input("Status-Text", value=str(product["status"]))
        with c4:
            visible = st.checkbox("Auf der öffentlichen Seite anzeigen", value=product["visible"])
            button_label = st.text_input("Button-Beschriftung", value=str(product["button_label"]))
        button_url = st.text_input("Button-/Download-Link", value=str(product["button_url"]), placeholder="https://... oder /?dashboard=1")
        st.caption("Erlaubt sind http(s)-Links oder interne Pfade wie /?dashboard=1. Bei Coming Soon wird kein aktiver Download-Button angezeigt.")
        save = st.form_submit_button("Änderungen speichern", type="primary", use_container_width=True)
    if save:
        safe = _safe_url(button_url)
        if button_url.strip() and not safe:
            st.error("Der Link ist ungültig. Bitte eine vollständige http(s)-Adresse oder einen internen Pfad angeben.")
            return
        if not name.strip() or not description.strip():
            st.error("Produktname und Beschreibung dürfen nicht leer sein.")
            return
        payload = {
            "name": name.strip()[:80], "eyebrow": eyebrow.strip()[:80],
            "description": description.strip()[:500], "icon": icon.strip()[:8] or "✦",
            "accent": accent, "status_key": status_key, "status": status.strip()[:40],
            "visible": bool(visible), "button_label": button_label.strip()[:60] or "Mehr erfahren",
            "button_url": safe,
        }
        try:
            db.reference(f"{PRODUCTS_PATH}/{selected}").set(payload)
            st.success("Produkt-Einstellungen wurden gespeichert.")
            st.rerun()
        except Exception:
            st.error("Speichern fehlgeschlagen. Bitte Firebase-Verbindung und Admin-Berechtigung prüfen.")
    st.divider()
    st.markdown("### Vorschau")
    preview = dict(product)
    preview["name"] = product["name"]
    st.caption("Die öffentliche Produktseite nutzt dieselben Karten und Inhalte.")
    st.markdown(_product_card(preview, 0), unsafe_allow_html=True)
    st.markdown("### Sichtbarkeit")
    st.write("Nur die hier aktivierten Produkte erscheinen öffentlich. Die aktuelle Vorauswahl umfasst StreamDex, StreamDex Mod Control und StreamDex Arcaid.")
