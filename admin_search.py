"""Globale Suche über StreamDex-, Lurk- und Mod-Control-Clients."""
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from firebase_admin import db

TZ = ZoneInfo("Europe/Berlin")
ONLINE_STALE_SECONDS = 150


def _dict(value):
    return value if isinstance(value, dict) else {}


def _num(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError, OverflowError):
        return 0


def _time(value):
    stamp = _num(value)
    if not stamp:
        return "—"
    try:
        return datetime.fromtimestamp(stamp / 1000, TZ).strftime("%d.%m.%Y %H:%M:%S")
    except (ValueError, OverflowError, OSError):
        return "—"


def _is_online(record, now_ms):
    seen = _num(record.get("last_seen"))
    return record.get("status") == "online" and seen > 0 and 0 <= now_ms - seen <= ONLINE_STALE_SECONDS * 1000


@st.cache_data(ttl=20, show_spinner=False)
def _load_clients():
    presence = _dict(db.reference("presence").get())
    lurk = _dict(db.reference("lurk/presence").get())
    bans_tw = _dict(db.reference("bans/twitch").get())
    bans_hw = _dict(db.reference("bans/hwid").get())
    now_ms = int(time.time() * 1000)
    rows = []

    def add(source, tid, record):
        if not isinstance(record, dict):
            return
        tid = str(tid or record.get("twitch_id") or "")
        if not tid:
            return
        hashes = [
            str(record.get(key) or "").lower()
            for key in ("hw_machine", "hw_board")
            if len(str(record.get(key) or "")) == 64
        ]
        hw_banned = any(value in bans_hw for value in hashes)
        online = _is_online(record, now_ms)
        rows.append({
            "Produkt": source,
            "Streamer": str(record.get("twitch_username") or tid),
            "Twitch-ID": tid,
            "Status": "Online" if online else ("Blockiert" if record.get("status") == "blocked" else "Offline"),
            "Version": str(record.get("app_version") or "—"),
            "Letzter Kontakt": _time(record.get("last_seen")),
            "Sperre": "Twitch" if tid in bans_tw else ("Hardware" if hw_banned else "—"),
            "_online": online,
        })

    for key, record in presence.items():
        if str(key).startswith("mod_"):
            add("Mod Control", record.get("twitch_id") if isinstance(record, dict) else "", record)
        else:
            add("StreamDex", key, record)
    for tid, record in lurk.items():
        add("Lurk", tid, record)

    rows.sort(key=lambda row: (not row["_online"], row["Streamer"].casefold(), row["Produkt"]))
    return rows


def render_admin_search():
    st.markdown("## 🔎 Globale Nutzer- & Client-Suche")
    st.caption("Ein Suchfeld für StreamDex Core, Lurk und Mod Control. Ergebnisse zeigen keine Geräte-Hashes oder Zugangsdaten.")
    if st.button("🔄 Suchdaten aktualisieren", key="admin_search_refresh"):
        _load_clients.clear()
        st.rerun()
    try:
        rows = _load_clients()
    except Exception:
        st.error("Die Nutzerdaten konnten nicht geladen werden. Bitte Firebase-Verbindung prüfen.")
        return

    c = st.columns(3)
    c[0].metric("Accounts / Clients", len(rows))
    c[1].metric("Online", sum(1 for row in rows if row["_online"]))
    c[2].metric("Gesperrt", sum(1 for row in rows if row["Sperre"] != "—"))

    q_col, app_col, status_col = st.columns([2, 1, 1])
    with q_col:
        query = st.text_input("Suchen", placeholder="Twitch-Name, Twitch-ID oder Version …", key="admin_global_search").strip().casefold()
    with app_col:
        product_filter = st.multiselect("Produkt", ["StreamDex", "Lurk", "Mod Control"], default=["StreamDex", "Lurk", "Mod Control"], key="admin_global_search_products")
    with status_col:
        status_filter = st.multiselect("Status", ["Online", "Offline", "Blockiert"], default=["Online", "Offline", "Blockiert"], key="admin_global_search_status")

    shown = [
        row for row in rows
        if row["Produkt"] in product_filter
        and row["Status"] in status_filter
        and (
            not query
            or query in row["Streamer"].casefold()
            or query in row["Twitch-ID"].casefold()
            or query in row["Version"].casefold()
        )
    ]
    st.caption(f"{len(shown)} Treffer")
    if shown:
        visible = [{key: value for key, value in row.items() if not key.startswith("_")} for row in shown]
        st.dataframe(pd.DataFrame(visible), hide_index=True, use_container_width=True)
    else:
        st.info("Keine passenden Accounts oder Clients gefunden.")
