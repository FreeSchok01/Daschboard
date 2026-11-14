"""Erweiterbarer Produktkatalog für die StreamDex OS-Verwaltung."""
import time

import streamlit as st
from firebase_admin import db


PRODUCT_CATALOG = [
    {
        "key": "streamdex",
        "name": "StreamDex OS",
        "kind": "Core-Plattform",
        "state": "integrated",
        "description": "Zentrale Streamer-Plattform mit Benutzer-, Lizenz-, Community- und Support-Verwaltung.",
        "source": "presence",
    },
    {
        "key": "lurk",
        "name": "StreamDex Lurk",
        "kind": "Desktop-Tool",
        "state": "integrated",
        "description": "Separater Lurk-Client mit eigener Presence und eigener Verwaltung.",
        "source": "lurk/presence",
    },
    {
        "key": "mod_control",
        "name": "StreamDex Mod Control",
        "kind": "Desktop-Tool",
        "state": "integrated",
        "description": "Moderations-Client-Verwaltung mit Versionen, Geräteinformationen und Sperren.",
        "source": "presence/mod_*",
    },
    {
        "key": "events",
        "name": "StreamDex Event Center",
        "kind": "Community-Modul",
        "state": "integrated",
        "description": "Community-Events, Teilnehmerlisten und Anmeldestatus.",
        "source": "streamdex_events",
    },
    {
        "key": "arcaid",
        "name": "StreamDex Arcaid",
        "kind": "Kommender Dienst",
        "state": "planned",
        "description": "Als zukünftiger StreamDex-Dienst bereits im Produktkatalog vorgesehen. Funktionen und Datenanbindung werden ergänzt, sobald der Umfang feststeht.",
        "source": None,
    },
]


def _dict(value):
    return value if isinstance(value, dict) else {}


def _online(value, now_ms):
    try:
        seen = int(value.get("last_seen") or 0)
        return value.get("status") == "online" and seen > 0 and 0 <= now_ms - seen <= 150_000
    except (TypeError, ValueError, OverflowError):
        return False


@st.cache_data(ttl=30, show_spinner=False)
def _catalog_counts():
    try:
        presence = _dict(db.reference("presence").get())
        lurk = _dict(db.reference("lurk/presence").get())
        events = _dict(db.reference("streamdex_events").get())
        now_ms = int(time.time() * 1000)
        core = {key: value for key, value in presence.items() if not str(key).startswith("mod_") and isinstance(value, dict)}
        mod = {key: value for key, value in presence.items() if str(key).startswith("mod_") and isinstance(value, dict)}
        lurk = {key: value for key, value in lurk.items() if isinstance(value, dict)}
        return {
            "connected": True,
            "streamdex": len(core),
            "streamdex_online": sum(1 for value in core.values() if _online(value, now_ms)),
            "lurk": len(lurk),
            "lurk_online": sum(1 for value in lurk.values() if _online(value, now_ms)),
            "mod_control": len(mod),
            "mod_online": sum(1 for value in mod.values() if _online(value, now_ms)),
            "events": len(events),
            "events_open": sum(1 for value in events.values() if isinstance(value, dict) and value.get("status", "open") == "open"),
        }
    except Exception:
        return {"connected": False}


def render_admin_registry():
    st.markdown("## 🧩 StreamDex Produktverwaltung")
    st.caption("Alle bestehenden und geplanten StreamDex-Dienste an einem Ort. Neue Produkte werden zentral im Produktkatalog registriert.")
    if st.button("🔄 Produktdaten aktualisieren", key="admin_registry_refresh"):
        _catalog_counts.clear()
        st.rerun()
    counts = _catalog_counts()

    if not counts.get("connected"):
        st.warning("Die Produktübersicht konnte die Firebase-Daten nicht vollständig laden. Die Produktstruktur wird trotzdem angezeigt.")

    st.markdown("### Produktportfolio")
    cols = st.columns(2, gap="large")
    for index, product in enumerate(PRODUCT_CATALOG):
        with cols[index % 2]:
            with st.container(border=True):
                title_col, state_col = st.columns([3, 1])
                with title_col:
                    st.markdown(f"### {product['name']}")
                    st.caption(product["kind"])
                with state_col:
                    if product["state"] == "planned":
                        st.warning("Geplant")
                    else:
                        st.success("Integriert")
                st.write(product["description"])
                if product["key"] == "streamdex" and counts.get("connected"):
                    st.metric("Registrierte StreamDex-Accounts", counts["streamdex"], f"{counts['streamdex_online']} mit Online-Status")
                elif product["key"] == "lurk" and counts.get("connected"):
                    st.metric("Registrierte Lurk-Clients", counts["lurk"], f"{counts['lurk_online']} mit Online-Status")
                elif product["key"] == "mod_control" and counts.get("connected"):
                    st.metric("Registrierte Mod-Control-Clients", counts["mod_control"], f"{counts['mod_online']} mit Online-Status")
                elif product["key"] == "events" and counts.get("connected"):
                    st.metric("Events", counts["events"], f"{counts['events_open']} offen")
                elif product["key"] == "arcaid":
                    st.info("Admin-Eintrag vorbereitet · Noch keine Live-Datenquelle verbunden.")
                st.caption(f"Interne Datenquelle: {product['source'] or 'Noch nicht festgelegt'}")

    st.divider()
    st.markdown("### Erweiterung um neue StreamDex-Dienste")
    st.write(
        "Jeder Dienst erhält einen eigenen Eintrag mit Produktstatus, Verwaltungsseite, Datenquelle und – sobald verfügbar – "
        "Live-Kennzahlen. So kann Arcaid später ergänzt werden, ohne die bestehende StreamDex-, Lurk- oder Mod-Control-Verwaltung umzubauen."
    )


def render_arcaid_admin():
    st.markdown("## 🗃️ StreamDex Arcaid")
    st.caption("Zukünftiger StreamDex-Dienst · Produktplatzhalter im Admin Control Center")
    st.info("StreamDex Arcaid ist im zentralen Produktkatalog angelegt. Die eigentliche Verwaltung bleibt bewusst noch leer, bis die Funktionen und die Datenstruktur des Produkts feststehen.")
    c = st.columns(3)
    c[0].metric("Produktstatus", "Geplant")
    c[1].metric("Admin-Anbindung", "Vorgesehen")
    c[2].metric("Live-Daten", "Noch nicht verbunden")
    st.markdown("### Vorbereitete Integrationspunkte")
    st.write(
        "Wenn Arcaid umgesetzt wird, können wir hier eine eigene Übersicht, Nutzerverwaltung, Versionsanzeige, "
        "Ereignisprotokolle, Berechtigungen und Produkt-Einstellungen ergänzen – passend zu den tatsächlichen Funktionen."
    )
    st.caption("Es werden aktuell keine Arcaid-Nutzer oder Funktionen simuliert und keine Arcaid-Daten geschrieben.")
