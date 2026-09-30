"""Statistik-Tab: Nutzer, Aktivität, Giveaways, Games, Versionen, Verkäufe."""
import time

import pandas as pd
import streamlit as st
from firebase_admin import db

STAT_KEYS = {
    "giveaways": "Giveaways", "giveaway_participants": "Teilnahmen", "giveaways_7d": "Giveaways 7 T",
    "giveaways_30d": "Giveaways 30 T", "viewers": "Viewer", "checkins": "Check-ins", "slot_spins": "Slot-Spins",
    "megaslot_spins": "Mega-Slot-Spins", "raids": "Raids", "fish_catches": "Fänge", "harvests": "Ernten",
}


@st.cache_data(ttl=60, show_spinner=False)
def _load():
    return (db.reference("stats").get() or {}, db.reference("game_flags").get() or {},
            db.reference("shop/orders").get() or {})


def stats_panel(rows, games):
    if st.button("🔄 Aktualisieren"):
        _load.clear()
    stats, flags, orders = _load()
    stats = {t: s for t, s in stats.items() if isinstance(s, dict)}
    now = time.time() * 1000

    def active(days):
        return sum(1 for r in rows if r["last_seen"] and now - r["last_seen"] <= days * 86400000)

    def total(k):
        return sum(int(s.get(k) or 0) for s in stats.values())

    st.subheader("👥 Nutzer")
    c = st.columns(6)
    c[0].metric("Registriert", len(rows))
    c[1].metric("Online jetzt", sum(1 for r in rows if r["online"]))
    c[2].metric("Aktiv 24 h", active(1))
    c[3].metric("Aktiv 7 T", active(7))
    c[4].metric("Aktiv 30 T", active(30))
    c[5].metric("Gesperrt", sum(1 for r in rows if r["banned"]))

    st.subheader("🎁 Giveaways & Community (Summe aller Streamer)")
    st.caption(f"{len(stats)} von {len(rows)} Streamern melden Statistiken (nur Apps mit Stats-Update).")
    keys = list(STAT_KEYS)
    for i in range(0, len(keys), 4):
        cols = st.columns(4)
        for col, k in zip(cols, keys[i:i + 4]):
            col.metric(STAT_KEYS[k], f"{total(k):,}".replace(",", "."))

    l, r_ = st.columns(2)
    with l:
        st.subheader("🏆 Top-Streamer (Giveaways)")
        names = {r["tid"]: r["name"] for r in rows}
        top = pd.Series({names.get(t, t): int(s.get("giveaways") or 0) for t, s in stats.items()}).sort_values(ascending=False).head(10)
        st.bar_chart(top) if not top.empty else st.info("Noch keine Daten.")
    with r_:
        st.subheader("🧩 App-Versionen")
        st.bar_chart(pd.Series([r["version"] for r in rows]).value_counts())

    st.subheader("🎮 Freigeschaltete Games (Streamer)")
    g_glob, g_own = flags.get("global") or {}, flags.get("streamers") or {}

    def has(tid, g):
        o = (g_own.get(tid) or {}).get(g)
        return o if isinstance(o, bool) else g_glob.get(g) is True
    st.bar_chart(pd.Series({games[g]: sum(1 for r in rows if has(r["tid"], g)) for g in games}))

    st.subheader("💶 Verkäufe")
    paid = [o for o in orders.values() if isinstance(o, dict) and o.get("status") == "paid"]
    c = st.columns(3)
    c[0].metric("Umsatz brutto", f"{sum(float(o['price']) for o in paid):.2f} €")
    c[1].metric("Bestellungen", len(paid))
    c[2].metric("Käufer", len({o['tid'] for o in paid}))

    st.subheader("📋 Pro Streamer")
    df = pd.DataFrame([{"Streamer": r["name"], "Online": r["online"], "Version": r["version"],
                        **{STAT_KEYS[k]: int((stats.get(r["tid"]) or {}).get(k) or 0) for k in STAT_KEYS}} for r in rows])
    st.dataframe(df.sort_values("Giveaways", ascending=False), hide_index=True, use_container_width=True)
