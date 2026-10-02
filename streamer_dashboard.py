"""Streamer-Dashboard mit geschütztem Zugriff über Einmal-Tokens."""
import secrets
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from firebase_admin import db

from shop import owned_games, CSS

TZ = ZoneInfo("Europe/Berlin")
SERVER_TS = {".sv": "timestamp"}

STAT_KEYS = {
    "giveaways": "Giveaways gesamt",
    "giveaway_participants": "Teilnahmen",
    "giveaways_7d": "Giveaways (7 Tage)",
    "giveaways_30d": "Giveaways (30 Tage)",
    "viewers": "Viewer erfasst",
    "checkins": "Check-ins",
    "slot_spins": "Slot-Spins",
    "megaslot_spins": "Mega-Slot-Spins",
    "fish_catches": "Fänge (Angeln)",
    "harvests": "Ernten (Farm)",
    "raids": "Raids empfangen",
}


def _fmt_ts(ms):
    try:
        return datetime.fromtimestamp(int(ms) / 1000, TZ).strftime("%d.%m.%Y %H:%M")
    except Exception:
        return ""


def _fmt_ago(ms):
    if not ms:
        return "nie"
    diff = max(0, int((time.time() * 1000 - int(ms)) / 1000))
    if diff < 60:
        return f"vor {diff} s"
    if diff < 3600:
        return f"vor {diff // 60} min"
    if diff < 86400:
        return f"vor {diff // 3600} h"
    return f"vor {diff // 86400} d"


def _verify_and_consume_token(token: str):
    """Prüft einen Login-Token aus Firebase und löscht ihn nach Verwendung."""
    if not token or len(token) < 16:
        return None
    
    ref = db.reference(f"dash_tokens/{token}")
    data = ref.get()
    
    if not isinstance(data, dict):
        return None
    
    # Prüfen ob Token abgelaufen ist (z.B. nach 5 Minuten = 300.000 ms)
    created_at = int(data.get("ts") or 0)
    now_ms = int(time.time() * 1000)
    
    # Token löschen (Einmal-Nutzung)
    ref.delete()
    
    if now_ms - created_at > 300000:
        return None  # Abgelaufen
        
    return str(data.get("tid"))


def _load_messages(tid):
    data = db.reference(f"chats/{tid}/messages").order_by_child("ts").limit_to_last(100).get() or {}
    msgs = [dict(v, id=k) for k, v in data.items() if isinstance(v, dict)]
    msgs.sort(key=lambda m: (int(m.get("ts") or 0), m["id"]))
    return msgs


def _send_message(tid, name, text):
    text = text.strip()[:2000]
    if not text:
        return
    db.reference(f"chats/{tid}/messages").push({"sender": "streamer", "name": name, "text": text, "ts": SERVER_TS})
    db.reference(f"chat_meta/{tid}").update({"last_ts": SERVER_TS, "last_sender": "streamer", "last_text": text[:100]})


def render_streamer_dashboard(games):
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown(
        '<div class="hero"><h1>📊 Streamer Dashboard</h1><p>Verwalte deine Freischaltungen, Statistiken und Support-Tickets.</p></div>',
        unsafe_allow_html=True,
    )

    # 1. Token aus URL verarbeiten (falls vorhanden)
    token_arg = st.query_params.get("token")
    if token_arg:
        valid_tid = _verify_and_consume_token(token_arg)
        if valid_tid:
            st.session_state["authenticated_tid"] = valid_tid
            # Token aus URL entfernen für saubere Adresse
            st.query_params.clear()
            st.query_params["dashboard"] = "1"
            st.rerun()
        else:
            st.error("Der Zugriffs-Link ist ungültig oder abgelaufen. Bitte öffne das Dashboard erneut über deine Streamdex Desktop-App.")

    # 2. Prüfen ob Streamer eingeloggt ist
    authed_tid = st.session_state.get("authenticated_tid")

    if not authed_tid:
        st.warning("🔒 Zugriffsgeschützter Bereich")
        st.info(
            "Bitte öffne das Dashboard direkt aus deiner **Streamdex Desktop-App**, "
            "um dich automatisch und sicher zu authentifizieren."
        )
        
        # Abmeldung / Reset-Button falls Sitzung hängen geblieben ist
        if st.button("Sitzung zurücksetzen"):
            st.session_state.pop("authenticated_tid", None)
            st.rerun()
        return

    # Daten des authentifizierten Streamers laden
    presence = db.reference(f"presence/{authed_tid}").get() or {}
    if not presence:
        st.error("Konto-Daten konnten nicht geladen werden.")
        return

    twitch_username = presence.get("twitch_username", authed_tid)
    app_version = presence.get("app_version", "?")
    last_seen = presence.get("last_seen")
    is_online = presence.get("status") == "online" and last_seen and (time.time() * 1000 - last_seen) < 150000

    have_games = owned_games(authed_tid)
    beta_info = db.reference(f"shop/beta/{authed_tid}").get() or {}
    stats_data = db.reference(f"stats/{authed_tid}").get() or {}

    # Header & Abmelden-Button
    top_col1, top_col2 = st.columns([5, 1])
    top_col1.caption(f"Angemeldet als: **{twitch_username}** (`{authed_tid}`)")
    if top_col2.button("🚪 Abmelden", key="dash_logout"):
        st.session_state.pop("authenticated_tid", None)
        st.rerun()

    # Key Performance Indicators
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Status", "🟢 Online" if is_online else "⚪ Offline", delta=f"Aktiv { _fmt_ago(last_seen) }")
    c2.metric("App-Version", app_version)
    c3.metric("Freigeschaltete Games", f"{len(have_games)} / {len(games)}")
    c4.metric("Beta-Status", "🧪 Aktiv" if beta_info else "Nein")

    st.divider()

    t_games, t_stats, t_support = st.tabs(["🎮 Freigeschaltete Games", "📈 Kanal-Statistiken", "💬 Support-Chat"])

    # --- Tab 1: Games ---
    with t_games:
        st.subheader("🎮 Deine Games & Features")
        cols = st.columns(3)
        for idx, (g_key, g_name) in enumerate(games.items()):
            is_unlocked = g_key in have_games
            with cols[idx % 3]:
                with st.container(border=True):
                    if is_unlocked:
                        st.markdown(f"### {g_name}")
                        st.markdown('<span class="badge">✅ Freigeschaltet</span>', unsafe_allow_html=True)
                    else:
                        st.markdown(f"### {g_name}")
                        st.markdown('<span class="badge save" style="background:#ef444422;color:#f87171;">🔒 Gesperrt</span>', unsafe_allow_html=True)
                        st.link_button("🛒 Im Shop freischalten", f"/?u={twitch_username}", use_container_width=True)

    # --- Tab 2: Stats ---
    with t_stats:
        st.subheader("📈 Deine Streamdex-Statistiken")
        if not stats_data:
            st.info("Noch keine statistischen Daten vorhanden.")
        else:
            s_cols = st.columns(3)
            for i, (k, label) in enumerate(STAT_KEYS.items()):
                val = int(stats_data.get(k) or 0)
                s_cols[i % 3].metric(label, f"{val:,}".replace(",", "."))

    # --- Tab 3: Support ---
    with t_support:
        st.subheader("💬 Direkt-Support")
        msgs = _load_messages(authed_tid)
        chat_box = st.container(height=400, border=True)
        with chat_box:
            if not msgs:
                st.caption("Noch keine Nachrichten vorhanden.")
            for m in msgs:
                is_admin = m.get("sender") == "admin"
                with st.chat_message("assistant" if is_admin else "user"):
                    st.caption(f"{'Support' if is_admin else twitch_username} · {_fmt_ts(m.get('ts'))}")
                    st.write(m.get("text", ""))

        prompt = st.chat_input("Nachricht an den Support senden ...")
        if prompt:
            _send_message(authed_tid, twitch_username, prompt)
            st.rerun()
