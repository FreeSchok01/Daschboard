"""Streamer-Dashboard für einzelne Streamer (/?dashboard=1 oder /?streamer=1).

Ermöglicht Streamern die Einsicht in:
- App- & Verbindungsstatus
- Freigeschaltete Games & Abkürzung zum Shop
- Kanal-Statistiken (Giveaways, Spins, Fänge, etc.)
- Direkt-Support-Chat mit dem Team
"""
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from firebase_admin import db

from shop import find_streamer, owned_games, CSS

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


def _streamer_stats(tid):
    return db.reference(f"stats/{tid}").get() or {}


def _streamer_beta(tid):
    return db.reference(f"shop/beta/{tid}").get() or {}


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
        '<div class="hero"><h1>📊 Streamer Dashboard</h1><p>Übersicht über deine freigeschalteten Games, Statistiken und Support.</p>'
        '<div class="steps"><span>Status prüfen</span><span>Games einsehen</span><span>Kanal-Stats</span><span>Support-Chat</span></div></div>',
        unsafe_allow_html=True,
    )

    name = st.text_input(
        "Dein Twitch-Name",
        value=str(st.query_params.get("u", "")),
        placeholder="z.B. meinkanal",
        key="dash_name_input",
    )

    if not name.strip():
        st.info("Bitte gib deinen Twitch-Namen ein, um deine Übersicht zu laden.")
        return

    tid, presence = find_streamer(name)
    if not tid or not presence:
        st.error("Kein Streamdex-Konto für diesen Namen gefunden. Starte die Streamdex-App mindestens einmal mit deinem Twitch-Account.")
        return

    twitch_username = presence.get("twitch_username", name)
    app_version = presence.get("app_version", "?")
    last_seen = presence.get("last_seen")
    is_online = presence.get("status") == "online" and last_seen and (time.time() * 1000 - last_seen) < 150000

    have_games = owned_games(tid)
    beta_info = _streamer_beta(tid)
    stats_data = _streamer_stats(tid)

    st.caption(f"Konto: **{twitch_username}** · Twitch-ID `{tid}`")

    # Kennzahlen
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Status", "🟢 Online" if is_online else "⚪ Offline", delta=f"Aktiv { _fmt_ago(last_seen) }")
    c2.metric("App-Version", app_version)
    c3.metric("Freigeschaltete Games", f"{len(have_games)} / {len(games)}")
    c4.metric("Beta-Status", "🧪 Aktiv" if beta_info else "Nein")

    st.divider()

    t_games, t_stats, t_support = st.tabs(["🎮 Freigeschaltete Games", "📈 Kanal-Statistiken", "💬 Support-Chat"])

    # ------------------------------------------------------------------------
    # Tab 1: Games
    # ------------------------------------------------------------------------
    with t_games:
        st.subheader("🎮 Deine Games & Features")
        st.caption("Freischaltungen sind nach dem Kauf oder der Freigabe innerhalb von ~60 Sekunden in deiner App aktiv.")

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

    # ------------------------------------------------------------------------
    # Tab 2: Statistiken
    # ------------------------------------------------------------------------
    with t_stats:
        st.subheader("📈 Deine Streamdex-Statistiken")
        if not stats_data:
            st.info("Noch keine statistischen Daten erfasst. Starte Giveaways oder Chat-Games in der App, um Statistiken zu sammeln.")
        else:
            s_cols = st.columns(3)
            for i, (k, label) in enumerate(STAT_KEYS.items()):
                val = int(stats_data.get(k) or 0)
                s_cols[i % 3].metric(label, f"{val:,}".replace(",", "."))

    # ------------------------------------------------------------------------
    # Tab 3: Direct Support Chat
    # ------------------------------------------------------------------------
    with t_support:
        st.subheader("💬 Direkt-Support")
        st.caption("Hast du Fragen oder Probleme? Schreibe direkt mit unserem Support-Team.")

        msgs = _load_messages(tid)
        chat_box = st.container(height=400, border=True)
        with chat_box:
            if not msgs:
                st.caption("Noch keine Nachrichten vorhanden.")
            for m in msgs:
                is_admin = m.get("sender") == "admin"
                with st.chat_message("assistant" if is_admin else "user"):
                    st.caption(f"{' Support' if is_admin else twitch_username} · {_fmt_ts(m.get('ts'))}")
                    st.write(m.get("text", ""))

        prompt = st.chat_input("Nachricht an den Support senden ...")
        if prompt:
            _send_message(tid, twitch_username, prompt)
            st.rerun()