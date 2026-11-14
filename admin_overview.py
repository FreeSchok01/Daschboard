"""Zentrale StreamDex OS Admin-Übersicht."""
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


def _read(path):
    try:
        return _dict(db.reference(path).get())
    except Exception:
        return {}


def _number(value, default=0):
    try:
        return int(float(value or 0))
    except (TypeError, ValueError, OverflowError):
        return default


def _time(value):
    stamp = _number(value)
    if not stamp:
        return "—"
    if stamp < 10_000_000_000:
        stamp *= 1000
    try:
        return datetime.fromtimestamp(stamp / 1000, TZ).strftime("%d.%m.%Y %H:%M")
    except (ValueError, OverflowError, OSError):
        return "—"


def _online(record, now_ms):
    seen = _number(record.get("last_seen"))
    return record.get("status") == "online" and seen > 0 and 0 <= now_ms - seen <= ONLINE_STALE_SECONDS * 1000


@st.cache_data(ttl=30, show_spinner=False)
def _snapshot():
    now_ms = int(time.time() * 1000)
    presence_all = _read("presence")
    mod_presence = {k: v for k, v in presence_all.items() if str(k).startswith("mod_") and isinstance(v, dict)}
    streamdex_presence = {k: v for k, v in presence_all.items() if not str(k).startswith("mod_") and isinstance(v, dict)}
    lurk_presence = _read("lurk/presence")
    stats = _read("stats")
    orders = _read("shop/orders")
    applications = _read("beta_applications")
    feedback = _read("feedback_inbox")
    events = _read("streamdex_events")
    bans_twitch = _read("bans/twitch")
    bans_hwid = _read("bans/hwid")
    supporters = _read("supporters")
    usage = _read("streamdex_tool_usage")

    def online_count(items):
        return sum(1 for value in items.values() if isinstance(value, dict) and _online(value, now_ms))

    paid_orders = [v for v in orders.values() if isinstance(v, dict) and v.get("status") == "paid"]
    revenue = 0.0
    for order in paid_orders:
        try:
            revenue += float(str(order.get("price") or "0").replace(",", "."))
        except (TypeError, ValueError):
            pass

    open_feedback = [v for v in feedback.values() if isinstance(v, dict) and v.get("status", "neu") in ("neu", "in Arbeit")]
    pending_beta = [v for v in applications.values() if isinstance(v, dict) and v.get("status", "pending") == "pending"]
    open_events = [v for v in events.values() if isinstance(v, dict) and v.get("status", "open") == "open"]
    event_participants = sum(
        len(_dict(event.get("participants")))
        for event in open_events
    )
    versions = {}
    for value in list(streamdex_presence.values()) + list(mod_presence.values()) + list(lurk_presence.values()):
        version = str(value.get("app_version") or "Unbekannt")
        versions[version] = versions.get(version, 0) + 1

    totals = {key: 0 for key in ("giveaways", "giveaway_participants", "viewers", "checkins", "slot_spins", "megaslot_spins", "raids", "fish_catches", "harvests")}
    for record in stats.values():
        if not isinstance(record, dict):
            continue
        for key in totals:
            totals[key] += _number(record.get(key))

    tool_totals = {}
    for user_data in usage.values():
        for key, record in _dict(user_data).items():
            if not isinstance(record, dict):
                continue
            item = tool_totals.setdefault(str(key), {"users": 0, "visits": 0})
            if _number(record.get("visit_count")) or _number(record.get("last_used_ms")):
                item["users"] += 1
                item["visits"] += _number(record.get("visit_count"))

    recent_feedback = []
    for key, record in feedback.items():
        if isinstance(record, dict):
            recent_feedback.append({
                "ID": str(key),
                "Typ": str(record.get("kind") or "Feedback"),
                "Streamer": str(record.get("streamer") or "Unbekannt"),
                "Status": str(record.get("status") or "neu"),
                "Eingegangen": _time(record.get("ts")),
                "_ts": _number(record.get("ts")),
                "Text": str(record.get("text") or "")[:180],
            })
    recent_feedback.sort(key=lambda row: row["_ts"], reverse=True)

    return {
        "streamdex_total": len(streamdex_presence),
        "streamdex_online": online_count(streamdex_presence),
        "lurk_total": len(lurk_presence),
        "lurk_online": online_count(lurk_presence),
        "mod_total": len(mod_presence),
        "mod_online": online_count(mod_presence),
        "stats_streamers": len(stats),
        "bans_twitch": len(bans_twitch),
        "bans_hwid": len(bans_hwid),
        "paid_orders": len(paid_orders),
        "revenue": revenue,
        "pending_beta": len(pending_beta),
        "open_feedback": len(open_feedback),
        "open_events": len(open_events),
        "event_participants": event_participants,
        "supporters": sum(1 for v in supporters.values() if isinstance(v, dict) and v.get("active", True)),
        "versions": versions,
        "totals": totals,
        "tools": tool_totals,
        "recent_feedback": recent_feedback[:8],
        "refreshed": now_ms,
    }


def render_admin_overview():
    st.markdown("## ⚡ StreamDex OS Control Center")
    st.caption("Zentrale Live-Übersicht über deine StreamDex-Dienste, Community, Shop und Support.")
    if st.button("🔄 Daten aktualisieren", key="admin_overview_refresh"):
        _snapshot.clear()
        st.rerun()

    try:
        data = _snapshot()
    except Exception:
        st.error("Die Admin-Übersicht konnte nicht geladen werden. Bitte Firebase-Verbindung und Server-Secrets prüfen.")
        return

    st.caption(f"Letzte Aktualisierung: {_time(data['refreshed'])} · Online-Status nach maximal {ONLINE_STALE_SECONDS} Sekunden ohne Heartbeat.")
    st.markdown("### Dienste")
    c = st.columns(4)
    c[0].metric("⚡ StreamDex", f"{data['streamdex_online']} online", f"{data['streamdex_total']} registriert")
    c[1].metric("👁️ Lurk", f"{data['lurk_online']} online", f"{data['lurk_total']} registriert")
    c[2].metric("🛡️ Mod Control", f"{data['mod_online']} online", f"{data['mod_total']} registriert")
    c[3].metric("🗃️ StreamDex Arcaid", "Geplant", "Verwaltung vorbereitet")

    st.markdown("### Schnellzugriff")
    quick = st.columns(4)
    quick_targets = [
        ("🧩 Produktportfolio", "apps"),
        ("🎉 Event Center", "events"),
        ("🩺 Systemstatus", "system"),
        ("🗃️ Arcaid", "arcaid"),
    ]
    for col, (label, target) in zip(quick, quick_targets):
        if col.button(label, key=f"overview_quick_{target}", use_container_width=True):
            st.session_state["admin_page"] = target
            st.rerun()

    st.markdown("### Was gerade Aufmerksamkeit braucht")
    c = st.columns(4)
    c[0].metric("🆕 Offenes Feedback", data["open_feedback"])
    c[1].metric("🧪 Beta-Prüfungen", data["pending_beta"])
    c[2].metric("🎉 Aktive Events", data["open_events"], f"{data['event_participants']} Anmeldungen")
    c[3].metric("🚫 Twitch-Sperren", data["bans_twitch"], f"{data['bans_hwid']} Hardware-Sperren")

    st.markdown("### Shop & Community")
    c = st.columns(4)
    c[0].metric("💶 Umsatz", f"{data['revenue']:,.2f} €".replace(",", "X").replace(".", ",").replace("X", "."))
    c[1].metric("🛒 Bezahlte Bestellungen", data["paid_orders"])
    c[2].metric("👥 Aktive Supporter", data["supporters"])
    c[3].metric("📊 Streamer mit Statistiken", data["stats_streamers"])

    st.divider()
    tab_activity, tab_usage, tab_versions = st.tabs(["📈 Community-Aktivität", "🧰 Tool-Nutzung", "📦 Versionen"])
    with tab_activity:
        totals = data["totals"]
        cols = st.columns(4)
        cols[0].metric("Giveaways", f"{totals['giveaways']:,}".replace(",", "."))
        cols[1].metric("Teilnahmen", f"{totals['giveaway_participants']:,}".replace(",", "."))
        cols[2].metric("Check-ins", f"{totals['checkins']:,}".replace(",", "."))
        cols[3].metric("Viewer", f"{totals['viewers']:,}".replace(",", "."))
        activity = pd.DataFrame([
            {"Aktion": label, "Anzahl": totals[key]}
            for key, label in [
                ("slot_spins", "Slot-Drehungen"), ("megaslot_spins", "Mega-Slot-Drehungen"),
                ("raids", "Raids"), ("fish_catches", "Angel-Fänge"), ("harvests", "Ernten"),
            ]
        ])
        if not activity.empty:
            st.bar_chart(activity.set_index("Aktion"))
    with tab_usage:
        if data["tools"]:
            usage_rows = [
                {"Tool": key, "Nutzer": value["users"], "Sitzungsöffnungen": value["visits"]}
                for key, value in sorted(data["tools"].items(), key=lambda item: item[1]["visits"], reverse=True)
            ]
            st.dataframe(pd.DataFrame(usage_rows), hide_index=True, use_container_width=True)
        else:
            st.info("Noch keine Tool-Nutzungsdaten vorhanden.")
    with tab_versions:
        if data["versions"]:
            rows = [{"Version": key, "Installationen": value} for key, value in sorted(data["versions"].items(), key=lambda item: item[1], reverse=True)]
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
            st.bar_chart(pd.DataFrame(rows).set_index("Version"))
        else:
            st.info("Noch keine Versionsdaten vorhanden.")

    st.divider()
    st.markdown("### 📨 Neueste Rückmeldungen")
    if data["recent_feedback"]:
        frame = pd.DataFrame(data["recent_feedback"]).drop(columns=["_ts"])
        st.dataframe(frame, hide_index=True, use_container_width=True)
    else:
        st.info("Noch keine Rückmeldungen eingegangen.")
