"""Adminbereich für StreamDex Mod Control."""
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from firebase_admin import db as firebase_db

TZ = ZoneInfo("Europe/Berlin")
ONLINE_STALE_SECONDS = 150
SERVER_TS = {".sv": "timestamp"}
HW_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def _fmt_time(value):
    try:
        return datetime.fromtimestamp(int(value) / 1000, TZ).strftime("%d.%m.%Y %H:%M:%S")
    except (TypeError, ValueError, OverflowError, OSError):
        return "—"


def _fmt_age(seconds):
    if seconds is None:
        return "Noch nie"
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"vor {seconds} Sek."
    if seconds < 3600:
        return f"vor {seconds // 60} Min."
    if seconds < 86400:
        return f"vor {seconds // 3600} Std."
    return f"vor {seconds // 86400} Tagen"


def _load_clients():
    presence = firebase_db.reference("presence").get() or {}
    bans_tw = firebase_db.reference("bans/twitch").get() or {}
    bans_hw = firebase_db.reference("bans/hwid").get() or {}
    presence = presence if isinstance(presence, dict) else {}
    bans_tw = bans_tw if isinstance(bans_tw, dict) else {}
    bans_hw = bans_hw if isinstance(bans_hw, dict) else {}
    now_ms = int(time.time() * 1000)
    rows = []

    for key, payload in presence.items():
        if not str(key).startswith("mod_") or not isinstance(payload, dict):
            continue
        tid = str(payload.get("twitch_id") or str(key)[4:]).strip()
        if not re.fullmatch(r"\d{1,20}", tid):
            continue
        try:
            last_seen = int(payload.get("last_seen") or 0)
        except (TypeError, ValueError):
            last_seen = 0
        age = (now_ms - last_seen) / 1000 if last_seen else None
        hashes = sorted({
            value.lower()
            for value in (payload.get("hw_machine"), payload.get("hw_board"))
            if isinstance(value, str) and HW_HASH_RE.fullmatch(value.lower())
        })
        rows.append({
            "tid": tid,
            "name": str(payload.get("twitch_username") or tid),
            "version": str(payload.get("app_version") or "Unbekannt"),
            "status": str(payload.get("status") or "unbekannt"),
            "online": payload.get("status") == "online" and age is not None and 0 <= age <= ONLINE_STALE_SECONDS,
            "last_seen": last_seen,
            "age": age,
            "app_name": str(payload.get("app_name") or "StreamDex Mod Control"),
            "uid": str(payload.get("uid") or ""),
            "hw": hashes,
            "banned": tid in bans_tw,
            "hw_banned": any(value in bans_hw for value in hashes),
            "session_start": payload.get("session_start"),
        })
    rows.sort(key=lambda r: (not r["online"], -r["last_seen"], r["name"].lower()))
    return rows, bans_tw, bans_hw


def _ban(row, reason, include_hw):
    reason = (reason or "").strip()[:300] or "Kein Grund angegeben."
    firebase_db.reference(f"bans/twitch/{row['tid']}").set({
        "reason": reason, "name": row["name"][:100], "ts": SERVER_TS,
    })
    if include_hw:
        for value in row["hw"]:
            firebase_db.reference(f"bans/hwid/{value}").set({
                "reason": reason, "tid": row["tid"], "name": row["name"][:100], "ts": SERVER_TS,
            })


def _unban(tid):
    firebase_db.reference(f"bans/twitch/{tid}").delete()
    hashes = firebase_db.reference("bans/hwid").get() or {}
    if isinstance(hashes, dict):
        for value, record in hashes.items():
            if isinstance(record, dict) and str(record.get("tid") or "") == str(tid):
                if HW_HASH_RE.fullmatch(str(value).lower()):
                    firebase_db.reference(f"bans/hwid/{value}").delete()


def render_mod_control_admin():
    st.header("🛡️ StreamDex Mod Control")
    st.caption("Desktop-Client-Verwaltung – getrennt von der normalen StreamDex-Presence.")
    try:
        rows, bans_tw, bans_hw = _load_clients()
    except Exception:
        st.error("Die Mod-Control-Daten konnten nicht aus Firebase geladen werden. Bitte Verbindung und Server-Secrets prüfen.")
        return

    versions = sorted({r["version"] for r in rows})
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Registrierte Clients", len(rows))
    c2.metric("Aktuell online", sum(1 for r in rows if r["online"]))
    c3.metric("Aktive Twitch-Sperren", len(bans_tw))
    c4.metric("Versionen im Einsatz", len(versions))

    st.divider()
    st.subheader("💻 Client-Übersicht")
    query = st.text_input("Client suchen", key="mod_control_search", placeholder="Twitch-Name, Twitch-ID oder Version …").strip().lower()
    only_online = st.toggle("Nur aktive Clients anzeigen", value=False, key="mod_control_only_online")
    shown = [
        r for r in rows
        if (not query or query in r["name"].lower() or query in r["tid"] or query in r["version"].lower())
        and (r["online"] or not only_online)
    ]
    if shown:
        st.dataframe(pd.DataFrame([{
            "Status": "🟢 Online" if r["online"] else "⚪ Offline",
            "Twitch": r["name"],
            "Twitch-ID": r["tid"],
            "Version": r["version"],
            "Letzter Kontakt": _fmt_age(r["age"]),
            "Sperre": "Twitch" if r["banned"] else ("Hardware" if r["hw_banned"] else "—"),
        } for r in shown]), hide_index=True, use_container_width=True)
    else:
        st.info("Keine passenden Mod-Control-Clients gefunden.")

    st.divider()
    st.subheader("🔎 Client verwalten")
    if not rows:
        st.info("Sobald sich jemand im StreamDex Mod Control anmeldet, erscheint der Client hier.")
    else:
        options = {f"{r['name']} · {r['tid']} · v{r['version']}": r for r in rows}
        label = st.selectbox("Client auswählen", list(options), key="mod_control_selected_client")
        row = options[label]
        a, b, c = st.columns(3)
        a.metric("Verbindungsstatus", "Online" if row["online"] else "Offline")
        b.metric("App-Version", row["version"])
        c.metric("Letzter Heartbeat", _fmt_age(row["age"]))
        st.write(f"Twitch-ID: {row['tid']}")
        st.write(f"App: {row['app_name']}")
        st.write(f"Letzter Kontakt: {_fmt_time(row['last_seen'])}")
        if row["session_start"]:
            st.write(f"Sitzungsbeginn: {_fmt_time(row['session_start'])}")
        if row["uid"]:
            st.caption(f"Firebase-UID: {row['uid']}")
        if row["hw"]:
            st.write("Registrierte Geräte-Hashes:")
            for value in row["hw"]:
                st.code(value, language=None)
        else:
            st.caption("Für diesen Client wurden keine Hardware-Hashes gemeldet.")

        if row["banned"] or row["hw_banned"]:
            st.warning("Für diesen Twitch-Account oder mindestens einen gemeldeten Geräte-Hash besteht bereits eine Sperre.")
            confirm = st.checkbox(f"Sperre für {row['name']} wirklich aufheben", key=f"mod_control_unban_confirm_{row['tid']}")
            if st.button("Sperre aufheben", disabled=not confirm, key=f"mod_control_unban_{row['tid']}"):
                try:
                    _unban(row["tid"])
                    st.success("Twitch- und zugehörige Hardware-Sperren wurden aufgehoben.")
                    st.rerun()
                except Exception:
                    st.error("Die Sperre konnte nicht aufgehoben werden.")
        else:
            with st.expander("🚫 Client / Benutzer sperren"):
                reason = st.text_input("Sperrgrund (wird dem Benutzer in der App angezeigt)", max_chars=300, key=f"mod_control_reason_{row['tid']}")
                include_hw = st.checkbox("Gemeldete Hardware-Hashes mitsperren", value=True, key=f"mod_control_hw_{row['tid']}")
                confirm = st.checkbox(f"Ich möchte {row['name']} ({row['tid']}) wirklich sperren.", key=f"mod_control_confirm_{row['tid']}")
                if st.button("Sperre aktivieren", type="primary", disabled=not confirm, key=f"mod_control_ban_{row['tid']}"):
                    try:
                        _ban(row, reason, include_hw)
                        st.success("Sperre wurde in Firebase gespeichert.")
                        st.rerun()
                    except Exception:
                        st.error("Die Sperre konnte nicht gespeichert werden. Bitte Firebase-Berechtigungen prüfen.")

    st.divider()
    st.subheader("📦 Installierte Versionen")
    if versions:
        counts = {}
        for row in rows:
            counts[row["version"]] = counts.get(row["version"], 0) + 1
        st.dataframe(pd.DataFrame([
            {"Version": version, "Installationen": count}
            for version, count in sorted(counts.items(), key=lambda item: item[0], reverse=True)
        ]), hide_index=True, use_container_width=True)
    else:
        st.info("Noch keine Versionsdaten vorhanden.")

    with st.expander("🚫 Aktive Sperren (alle)"):
        if not bans_tw and not bans_hw:
            st.caption("Keine aktiven Sperren.")
        for tid, record in bans_tw.items():
            record = record if isinstance(record, dict) else {}
            st.write(f"{record.get('name') or tid} · Twitch-ID {tid} · {_fmt_time(record.get('ts'))} · {record.get('reason') or 'Kein Grund angegeben.'}")
        st.caption(f"Zusätzlich gespeicherte Hardware-Sperren: {len(bans_hw)}")
