"""Release- und Sicherheitsübersicht für das StreamDex OS Control Center.

Die Seite arbeitet bewusst lesend: Sie erfindet keine Releases und verändert
keine Konten oder Sperren. Release-Metadaten werden nur angezeigt, wenn sie
unter app_releases/<product> tatsächlich hinterlegt sind.
"""
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from firebase_admin import db

TZ = ZoneInfo("Europe/Berlin")
STALE_MS = 150_000
PRODUCTS = [
    ("streamdex", "StreamDex OS", "presence", False),
    ("lurk", "StreamDex Lurk", "lurk/presence", False),
    ("mod_control", "StreamDex Mod Control", "presence", True),
    ("arcaid", "StreamDex Arcaid", None, False),
]


def _dict(value):
    return value if isinstance(value, dict) else {}


def _read(path):
    try:
        return db.reference(path).get()
    except Exception:
        return None


def _time(value):
    try:
        stamp = int(value or 0)
        if stamp < 10_000_000_000:
            stamp *= 1000
        return datetime.fromtimestamp(stamp / 1000, TZ).strftime("%d.%m.%Y %H:%M") if stamp else "—"
    except (TypeError, ValueError, OverflowError, OSError):
        return "—"


def _clients():
    core = _dict(_read("presence"))
    lurk = _dict(_read("lurk/presence"))
    now = int(time.time() * 1000)
    sources = {
        "streamdex": [v for k, v in core.items() if not str(k).startswith("mod_") and isinstance(v, dict)],
        "lurk": [v for v in lurk.values() if isinstance(v, dict)],
        "mod_control": [v for k, v in core.items() if str(k).startswith("mod_") and isinstance(v, dict)],
        "arcaid": [],
    }
    result = {}
    for key, _, _, _ in PRODUCTS:
        values = sources[key]
        online = sum(
            1 for item in values
            if item.get("status") == "online"
            and 0 < int(item.get("last_seen") or 0) <= now
            and now - int(item.get("last_seen") or 0) <= STALE_MS
        )
        versions = {}
        for item in values:
            version = str(item.get("app_version") or "Unbekannt")
            versions[version] = versions.get(version, 0) + 1
        result[key] = {"total": len(values), "online": online, "versions": versions}
    return result


def render_release_center():
    st.markdown("## 📦 Release & Versions-Center")
    st.caption("Installierte Client-Versionen und veröffentlichte Release-Metadaten – ohne Update-Zwang oder automatische Änderungen.")
    if st.button("🔄 Release-Daten aktualisieren", key="release_center_refresh"):
        st.cache_data.clear()
        st.rerun()

    try:
        clients = _clients()
    except Exception:
        st.error("Die installierten Versionen konnten nicht vollständig geladen werden.")
        clients = {}

    cols = st.columns(4)
    for col, (key, name, _, _) in zip(cols, PRODUCTS):
        item = clients.get(key, {"total": 0, "online": 0, "versions": {}})
        col.metric(name, f"{item['online']} online", f"{item['total']} registriert")
    st.divider()
    st.markdown("### Installierte Versionen")
    rows = []
    for key, name, _, _ in PRODUCTS:
        item = clients.get(key, {"versions": {}})
        if item["versions"]:
            for version, count in sorted(item["versions"].items()):
                rows.append({"Produkt": name, "Version": version, "Installationen": count})
        else:
            rows.append({"Produkt": name, "Version": "Keine Clientdaten", "Installationen": 0})
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    st.divider()
    st.markdown("### Release-Metadaten")
    st.caption("Optionale Datenquelle: app_releases/<produkt>. Es werden nur tatsächlich vorhandene Einträge angezeigt.")
    releases = _dict(_read("app_releases"))
    release_rows = []
    for key, name, _, _ in PRODUCTS:
        record = _dict(releases.get(key))
        if not record:
            release_rows.append({
                "Produkt": name, "Release": "Noch nicht hinterlegt",
                "Version": "—", "Veröffentlicht": "—", "Mindestversion": "—",
            })
            continue
        release_rows.append({
            "Produkt": name,
            "Release": str(record.get("status") or "Metadaten vorhanden"),
            "Version": str(record.get("version") or "—"),
            "Veröffentlicht": _time(record.get("published_at_ms") or record.get("published_at")),
            "Mindestversion": str(record.get("minimum_version") or "—"),
        })
    st.dataframe(pd.DataFrame(release_rows), hide_index=True, use_container_width=True)
    st.info("Diese Ansicht verteilt noch keine Updates. Ein späteres Update-System benötigt signierte Pakete, Prüfsummen, Rollback und einen expliziten Freigabeprozess.")


def render_security_center():
    st.markdown("## 🛡️ Sicherheits-Center")
    st.caption("Zentrale, datensparsame Übersicht über Sperren, Client-Status und Admin-Aktivitäten.")
    if st.button("🔄 Sicherheitsdaten aktualisieren", key="security_center_refresh"):
        st.cache_data.clear()
        st.rerun()

    try:
        twitch_bans = _dict(_read("bans/twitch"))
        hardware_bans = _dict(_read("bans/hwid"))
        core = _dict(_read("presence"))
        lurk = _dict(_read("lurk/presence"))
        audit = _dict(_read("admin_audit"))
    except Exception:
        st.error("Sicherheitsdaten konnten nicht geladen werden.")
        return

    mod = {k: v for k, v in core.items() if str(k).startswith("mod_") and isinstance(v, dict)}
    streamdex = {k: v for k, v in core.items() if not str(k).startswith("mod_") and isinstance(v, dict)}
    cols = st.columns(4)
    cols[0].metric("Twitch-Sperren", len(twitch_bans))
    cols[1].metric("Hardware-Sperren", len(hardware_bans))
    cols[2].metric("Registrierte Clients", len(streamdex) + len(lurk) + len(mod))
    cols[3].metric("Admin-Protokolle", len(audit))

    st.divider()
    st.markdown("### Aktive Twitch-Sperren")
    ban_rows = []
    for tid, raw in twitch_bans.items():
        record = _dict(raw)
        ban_rows.append({
            "Twitch-Name": str(record.get("name") or "Unbekannt"),
            "Twitch-ID": str(tid),
            "Grund": str(record.get("reason") or "Kein Grund angegeben"),
            "Zeitpunkt": _time(record.get("ts")),
        })
    if ban_rows:
        st.dataframe(pd.DataFrame(ban_rows), hide_index=True, use_container_width=True)
    else:
        st.success("Keine Twitch-Sperren gespeichert.")

    st.divider()
    st.markdown("### Sicherheits- und Datenschutz-Hinweise")
    st.write(
        "- Hardware-Hashes werden in dieser Übersicht absichtlich nicht angezeigt.\n"
        "- Firebase-Zugangstokens, OAuth-Tokens und private Schlüssel werden nicht geladen.\n"
        "- Sperren werden hier nur angezeigt; Änderungen erfolgen weiterhin in den jeweiligen Produkt-Verwaltungsseiten.\n"
        "- Die Admin-Aktivitäten sind nur so vollständig wie die Stellen, die write_admin_audit() aufrufen."
    )
    st.caption("Die Anzeige ist eine administrative Bestandsübersicht und kein automatischer Intrusion-Detection- oder Uptime-Dienst.")
