"""System- und Datenstatus des StreamDex OS Adminbereichs."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from firebase_admin import db

TZ = ZoneInfo("Europe/Berlin")

CHECKS = [
    ("StreamDex Presence", "presence", "Anmeldungen der Core-Plattform"),
    ("Lurk Presence", "lurk/presence", "Eigenständige Lurk-Clients"),
    ("Feedback", "feedback_inbox", "Bugs, Ideen und Rückmeldungen"),
    ("Beta-Bewerbungen", "beta_applications", "Eingegangene Bewerbungen"),
    ("Events", "streamdex_events", "Community-Events"),
    ("Shop-Bestellungen", "shop/orders", "Bestellhistorie"),
    ("Supporter", "supporters", "Supporter-Konten"),
    ("Tool-Nutzung", "streamdex_tool_usage", "Gespeicherte Tool-Aktivität"),
]


def _count(value):
    if isinstance(value, dict):
        return len(value)
    if isinstance(value, list):
        return sum(item is not None for item in value)
    return 0


@st.cache_data(ttl=30, show_spinner=False)
def _check_nodes():
    rows = []
    for label, path, description in CHECKS:
        try:
            value = db.reference(path).get()
            rows.append({
                "Bereich": label,
                "Datenbankpfad": path,
                "Status": "Erreichbar",
                "Einträge": _count(value),
                "Hinweis": description,
                "_ok": True,
            })
        except Exception as exc:
            rows.append({
                "Bereich": label,
                "Datenbankpfad": path,
                "Status": "Fehler",
                "Einträge": "—",
                "Hinweis": f"{description} · {type(exc).__name__}",
                "_ok": False,
            })
    return rows


def render_admin_system_status():
    st.markdown("## 🩺 System- & Datenstatus")
    st.caption("Prüft die Erreichbarkeit wichtiger Firebase-Datenbereiche. Das ist eine Datenbankprüfung, kein externer Uptime-Monitor.")
    if st.button("🔄 Prüfungen erneut ausführen", key="admin_system_refresh"):
        _check_nodes.clear()
        st.rerun()

    rows = _check_nodes()
    ok_count = sum(1 for row in rows if row["_ok"])
    bad_count = len(rows) - ok_count
    c = st.columns(3)
    c[0].metric("Geprüfte Datenbereiche", len(rows))
    c[1].metric("Erreichbar", ok_count)
    c[2].metric("Mit Fehler", bad_count)

    if bad_count:
        st.warning("Mindestens ein Firebase-Datenbereich konnte nicht gelesen werden. Details stehen in der Tabelle.")
    else:
        st.success("Alle geprüften Firebase-Datenbereiche waren erreichbar.")

    visible = [{key: value for key, value in row.items() if key != "_ok"} for row in rows]
    st.dataframe(pd.DataFrame(visible), hide_index=True, use_container_width=True)

    st.divider()
    st.markdown("### Was diese Prüfung abdeckt")
    st.write(
        "Die Prüfung liest ausschließlich die angegebenen Verwaltungsbereiche über den serverseitigen Firebase-Admin-Zugang. "
        "Sie verändert keine Daten und zeigt keine Zugangstokens, privaten Schlüssel oder Kennwörter an."
    )
    st.caption(f"Letzte Prüfung: {datetime.now(TZ).strftime('%d.%m.%Y %H:%M:%S')} · Cache maximal 30 Sekunden.");
