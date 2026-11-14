"""Globale Event-Verwaltung für den StreamDex OS Adminbereich."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from firebase_admin import db

TZ = ZoneInfo("Europe/Berlin")
EVENTS_PATH = "streamdex_events"


def _dict(value):
    return value if isinstance(value, dict) else {}


def _fmt_ts(value):
    try:
        stamp = int(value or 0)
        if stamp < 10_000_000_000:
            stamp *= 1000
        if not stamp:
            return "—"
        return datetime.fromtimestamp(stamp / 1000, TZ).strftime("%d.%m.%Y %H:%M")
    except (TypeError, ValueError, OverflowError, OSError):
        return "—"


def _load_events():
    root = db.reference(EVENTS_PATH).get() or {}
    if not isinstance(root, dict):
        return []
    rows = []
    for event_id, raw in root.items():
        if not isinstance(raw, dict):
            continue
        event = dict(raw)
        event["id"] = str(event_id)
        event["participants"] = _dict(event.get("participants"))
        rows.append(event)
    rows.sort(key=lambda row: int(row.get("created_ts") or 0), reverse=True)
    return rows


def render_admin_events():
    st.markdown("## 🎉 StreamDex Event Center")
    st.caption("Zentrale Verwaltung aller Community-Events – unabhängig davon, welcher Streamer sie erstellt hat.")
    try:
        events = _load_events()
    except Exception:
        st.error("Die Event-Daten konnten nicht geladen werden. Bitte Firebase-Verbindung prüfen.")
        return

    open_events = [event for event in events if event.get("status", "open") == "open"]
    closed_events = [event for event in events if event.get("status") == "closed"]
    participants_total = sum(len(event["participants"]) for event in events)

    c = st.columns(4)
    c[0].metric("Events gesamt", len(events))
    c[1].metric("Anmeldungen offen", len(open_events))
    c[2].metric("Geschlossene Events", len(closed_events))
    c[3].metric("Teilnahmen gesamt", participants_total)

    st.divider()
    q_col, status_col = st.columns([2, 1])
    with q_col:
        query = st.text_input("Event suchen", placeholder="Titel, Spiel, Ersteller oder ID …", key="admin_events_search").strip().casefold()
    with status_col:
        status_filter = st.multiselect("Status", ["open", "closed"], default=["open", "closed"], format_func=lambda value: "Offen" if value == "open" else "Geschlossen", key="admin_events_status")

    shown = []
    for event in events:
        owner = str(event.get("owner_name") or event.get("owner_tid") or "")
        haystack = " ".join((str(event.get("title") or ""), str(event.get("game") or ""), owner, event["id"])).casefold()
        if event.get("status", "open") not in status_filter:
            continue
        if query and query not in haystack:
            continue
        shown.append(event)

    if not shown:
        st.info("Keine passenden Events gefunden.")
        return

    for event in shown:
        event_id = event["id"]
        participants = event["participants"]
        is_open = event.get("status", "open") == "open"
        cap = int(event.get("capacity") or 0)
        count = len(participants)
        owner = str(event.get("owner_name") or "Unbekannt")
        title = str(event.get("title") or "Event ohne Titel")
        status_label = "🟢 Anmeldung offen" if is_open else "⚪ Geschlossen"
        with st.expander(f"{'🟢' if is_open else '⚪'} {title} · {count}{' / ' + str(cap) if cap else ''} Anmeldungen", expanded=False):
            left, right = st.columns([3, 1])
            with left:
                st.markdown(f"### {title}")
                st.caption(f"{status_label} · {event.get('event_type') or 'Event'} · {event.get('game') or 'Keine Kategorie'}")
                st.write(str(event.get("description") or "Keine Beschreibung hinterlegt."))
                st.write(f"**Ersteller:** {owner} · **Twitch-ID:** {event.get('owner_tid') or '—'}")
                st.write(f"**Termin:** {event.get('event_date') or 'Noch offen'}")
                st.write(f"**Erstellt:** {_fmt_ts(event.get('created_ts'))}")
                st.caption(f"Event-ID: {event_id}")
            with right:
                st.metric("Anmeldungen", f"{count}{' / ' + str(cap) if cap else ''}")
                if is_open:
                    if st.button("Anmeldung schließen", key=f"admin_event_close_{event_id}", use_container_width=True):
                        try:
                            db.reference(f"{EVENTS_PATH}/{event_id}/status").set("closed")
                            st.success("Anmeldung geschlossen.")
                            st.rerun()
                        except Exception:
                            st.error("Event konnte nicht aktualisiert werden.")
                else:
                    if st.button("Event wieder öffnen", key=f"admin_event_open_{event_id}", use_container_width=True):
                        try:
                            db.reference(f"{EVENTS_PATH}/{event_id}/status").set("open")
                            st.success("Event wieder geöffnet.")
                            st.rerun()
                        except Exception:
                            st.error("Event konnte nicht aktualisiert werden.")

            if participants:
                st.markdown("**Teilnehmerliste**")
                participant_rows = []
                for participant_id, participant in participants.items():
                    participant = _dict(participant)
                    participant_rows.append({
                        "Anzeigename": str(participant.get("display_name") or "Unbekannt"),
                        "Plattform": str(participant.get("platform") or "—"),
                        "Angemeldet": str(participant.get("registered_at") or "—"),
                        "_id": str(participant_id),
                    })
                st.dataframe(pd.DataFrame([{k: v for k, v in row.items() if k != "_id"} for row in participant_rows]), hide_index=True, use_container_width=True)
                participant_options = {
                    f"{row['Anzeigename']} · {row['Plattform']} · {row['_id']}": row["_id"]
                    for row in participant_rows
                }
                if participant_options:
                    remove_col, confirm_col = st.columns([2, 1])
                    selected_participant = remove_col.selectbox("Anmeldung entfernen", list(participant_options), key=f"admin_event_remove_pick_{event_id}")
                    confirm_remove = confirm_col.checkbox("Bestätigen", key=f"admin_event_remove_confirm_{event_id}")
                    if st.button("Teilnehmer entfernen", disabled=not confirm_remove, key=f"admin_event_remove_{event_id}"):
                        try:
                            db.reference(f"{EVENTS_PATH}/{event_id}/participants/{participant_options[selected_participant]}").delete()
                            st.success("Anmeldung entfernt.")
                            st.rerun()
                        except Exception:
                            st.error("Anmeldung konnte nicht entfernt werden.")
            else:
                st.caption("Noch keine Anmeldungen.")

            st.divider()
            confirm_delete = st.checkbox(f"Event „{title}“ einschließlich aller Anmeldungen endgültig löschen", key=f"admin_event_delete_confirm_{event_id}")
            if st.button("🗑️ Event löschen", type="primary", disabled=not confirm_delete, key=f"admin_event_delete_{event_id}"):
                try:
                    db.reference(f"{EVENTS_PATH}/{event_id}").delete()
                    st.success("Event und Anmeldungen wurden gelöscht.")
                    st.rerun()
                except Exception:
                    st.error("Event konnte nicht gelöscht werden.")
