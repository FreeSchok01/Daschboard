"""Audit-Protokoll für administrative Änderungen im StreamDex OS."""
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from firebase_admin import db

TZ = ZoneInfo("Europe/Berlin")
SERVER_TS = {".sv": "timestamp"}


def write_admin_audit(action, area, target="", actor="Support"):
    """Best-effort audit write. Audit failure must never block the actual admin action."""
    payload = {
        "action": str(action or "Änderung")[:80],
        "area": str(area or "Allgemein")[:60],
        "target": str(target or "—")[:120],
        "actor": str(actor or "Support")[:60],
        "ts": SERVER_TS,
        "created_ms": int(time.time() * 1000),
    }
    try:
        db.reference("admin_audit").push(payload)
        return True
    except Exception as exc:
        print(f"Admin audit write failed ({type(exc).__name__})")
        return False


def _format_time(value):
    try:
        stamp = int(value or 0)
        if stamp < 10_000_000_000:
            stamp *= 1000
        if not stamp:
            return "—"
        return datetime.fromtimestamp(stamp / 1000, TZ).strftime("%d.%m.%Y %H:%M:%S")
    except (TypeError, ValueError, OverflowError, OSError):
        return "—"


@st.cache_data(ttl=20, show_spinner=False)
def _load_audit():
    root = db.reference("admin_audit").order_by_child("created_ms").limit_to_last(500).get() or {}
    if not isinstance(root, dict):
        return []
    rows = []
    for key, record in root.items():
        if not isinstance(record, dict):
            continue
        rows.append({
            "ID": str(key),
            "Zeitpunkt": _format_time(record.get("created_ms") or record.get("ts")),
            "Bereich": str(record.get("area") or "Allgemein"),
            "Aktion": str(record.get("action") or "Änderung"),
            "Ziel": str(record.get("target") or "—"),
            "Administrator": str(record.get("actor") or "Support"),
            "_ts": int(record.get("created_ms") or 0),
        })
    rows.sort(key=lambda row: row["_ts"], reverse=True)
    return rows


def render_admin_audit():
    st.markdown("## 🧾 Admin-Aktivitätsprotokoll")
    st.caption("Nachvollziehbare Liste administrativer Änderungen. Es werden keine Passwörter, Tokens oder Hardware-Hashes protokolliert.")
    if st.button("🔄 Protokoll aktualisieren", key="admin_audit_refresh"):
        _load_audit.clear()
        st.rerun()
    try:
        rows = _load_audit()
    except Exception:
        st.error("Das Admin-Protokoll konnte nicht geladen werden. Prüfe die Firebase-Verbindung.")
        return
    c = st.columns(2)
    c[0].metric("Gespeicherte Aktionen", len(rows))
    c[1].metric("Aufbewahrte Einträge", "Letzte 500")

    if not rows:
        st.info("Sobald eine unterstützte Admin-Aktion ausgeführt wird, erscheint sie hier.")
        return
    f1, f2 = st.columns(2)
    areas = sorted({row["Bereich"] for row in rows})
    with f1:
        selected_areas = st.multiselect("Bereiche", areas, default=areas, key="admin_audit_areas")
    with f2:
        query = st.text_input("Protokoll durchsuchen", placeholder="Aktion, Ziel oder Administrator …", key="admin_audit_search").casefold().strip()
    filtered = [
        row for row in rows
        if row["Bereich"] in selected_areas
        and (not query or query in " ".join(str(row[key]) for key in ("Aktion", "Ziel", "Administrator", "Bereich")).casefold())
    ]
    if filtered:
        st.dataframe(pd.DataFrame([{key: value for key, value in row.items() if key not in ("ID", "_ts")} for row in filtered]), hide_index=True, use_container_width=True)
    else:
        st.info("Keine passenden Protokolleinträge.")
