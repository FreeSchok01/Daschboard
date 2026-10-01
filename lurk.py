"""StreamDex Lurk (Dashboard): Statistiken, Support-Chat, Reports und Sperren für die Lurk-App.

Firebase-Pfade: lurk/presence, lurk/chats, lurk/chat_meta, lurk/stats (geschrieben von der Lurk-App).
Sperren (bans/*) und Reports (feedback_inbox, Version beginnt mit "Lurk") sind mit StreamDex geteilt.
"""
import time

import pandas as pd
import streamlit as st
from firebase_admin import db

from feedback_inbox import feedback_panel

NS = "lurk"
STAT_KEYS = {
    "channels": "Kanäle", "favorites": "Favoriten", "auto_open": "Auto-Open", "auto_commands": "Auto-Befehle",
    "watch_hours": "Lurk-Stunden", "watched_channels": "Kanäle mit Lurk-Zeit", "streams_open": "Live-Kanäle (gelurkt)",
}


@st.cache_data(ttl=60, show_spinner=False)
def _load_stats():
    return db.reference(f"{NS}/stats").get() or {}


def _num(v):
    try:
        return float(v or 0)
    except Exception:
        return 0.0


def lurk_stats(rows):
    if st.button("🔄 Aktualisieren", key="lurk_stats_refresh"):
        _load_stats.clear()
    stats = {t: s for t, s in _load_stats().items() if isinstance(s, dict)}
    now = time.time() * 1000

    def active(days):
        return sum(1 for r in rows if r["last_seen"] and now - r["last_seen"] <= days * 86400000)

    st.subheader("👥 Nutzer")
    c = st.columns(6)
    c[0].metric("Registriert", len(rows))
    c[1].metric("Online jetzt", sum(1 for r in rows if r["online"]))
    c[2].metric("Aktiv 24 h", active(1))
    c[3].metric("Aktiv 7 T", active(7))
    c[4].metric("Aktiv 30 T", active(30))
    c[5].metric("Gesperrt", sum(1 for r in rows if r["banned"]))

    st.subheader("👁️ Nutzung (Summe aller Nutzer)")
    st.caption(f"{len(stats)} von {len(rows)} Nutzern melden Statistiken (alle 10 Minuten, nur anonyme Summen).")
    keys = list(STAT_KEYS)
    for i in range(0, len(keys), 4):
        cols = st.columns(4)
        for col, k in zip(cols, keys[i:i + 4]):
            total = sum(_num(s.get(k)) for s in stats.values())
            col.metric(STAT_KEYS[k], f"{total:,.1f}".replace(",", ".") if k == "watch_hours" else f"{int(total):,}".replace(",", "."))

    l, r_ = st.columns(2)
    with l:
        st.subheader("🏆 Top-Nutzer (Lurk-Stunden)")
        names = {r["tid"]: r["name"] for r in rows}
        if stats:
            top = pd.Series({names.get(t, t): _num(s.get("watch_hours")) for t, s in stats.items()}).sort_values(ascending=False).head(10)
            st.bar_chart(top)
        else:
            st.info("Noch keine Daten.")
    with r_:
        st.subheader("🧩 App-Versionen")
        if rows:
            st.bar_chart(pd.Series([r["version"] for r in rows]).value_counts())
        else:
            st.info("Noch keine Nutzer.")

    st.subheader("📋 Pro Nutzer")
    if rows:
        df = pd.DataFrame([{"Nutzer": r["name"], "Online": r["online"], "Version": r["version"],
                            **{STAT_KEYS[k]: _num((stats.get(r["tid"]) or {}).get(k)) for k in STAT_KEYS}} for r in rows])
        st.dataframe(df.sort_values("Lurk-Stunden", ascending=False), hide_index=True, use_container_width=True)


def lurk_panel(*, load_streamers, streamer_list, chat_panel, bans_panel, fb_label, me):
    t_stats, t_chat, t_fb, t_bans = st.tabs(["📊 Statistiken", "💬 Support-Chat", fb_label(), "🚫 Sperren"])
    with t_stats:
        try:
            lurk_stats(load_streamers(NS))
        except Exception as e:
            st.error(f"Firebase-Fehler: {e}")
    with t_chat:
        left, right = st.columns([1, 2], gap="large")
        with left:
            st.subheader("Nutzer")
            search = st.text_input("Suche", placeholder="Twitch-Name ...", label_visibility="collapsed", key="lurk_search")
            only_online = st.toggle("Nur online", value=False, key="lurk_only_online")
            streamer_list(search, only_online, NS)
        with right:
            try:
                rows_by_tid = {r["tid"]: r for r in load_streamers(NS)}
            except Exception:
                rows_by_tid = {}
            chat_panel(rows_by_tid, ns=NS)
    with t_fb:
        feedback_panel(me, is_admin=True, tool="lurk")
    with t_bans:
        bans_panel(NS)
