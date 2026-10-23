"""StreamDex Events: Eventverwaltung und öffentliche Anmeldung via Firebase Realtime Database."""
import re
import secrets
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st
from firebase_admin import db

TZ = ZoneInfo("Europe/Berlin")
EVENTS_PATH = "streamdex_events"
SLUG_RE = re.compile(r"^[A-Za-z0-9_-]{6,40}$")


def _now_label():
    return datetime.now(TZ).strftime("%d.%m.%Y %H:%M")


def _event_ref(event_id):
    if not isinstance(event_id, str) or not SLUG_RE.fullmatch(event_id):
        return None
    return db.reference(f"{EVENTS_PATH}/{event_id}")


def _load_events(owner_tid=None, include_closed=True):
    data = db.reference(EVENTS_PATH).get() or {}
    result = []
    if not isinstance(data, dict):
        return result
    for event_id, event in data.items():
        if not isinstance(event, dict):
            continue
        if owner_tid and str(event.get("owner_tid")) != str(owner_tid):
            continue
        if not include_closed and event.get("status") != "open":
            continue
        event = dict(event)
        event["id"] = event_id
        result.append(event)
    result.sort(key=lambda e: str(e.get("created_at", "")), reverse=True)
    return result


def _participant_list(event):
    participants = event.get("participants") or {}
    if not isinstance(participants, dict):
        return []
    rows = []
    for pid, p in participants.items():
        if isinstance(p, dict):
            rows.append({"id": pid, **p})
    rows.sort(key=lambda p: str(p.get("registered_at", "")))
    return rows


def render_event_manager(owner_tid, twitch_username):
    st.subheader("🎉 StreamDex Events")
    st.caption("Erstelle Community-Events und teile den öffentlichen Anmeldelink. Die Anmeldung wird in Firebase gespeichert.")
    with st.expander("➕ Neues Event erstellen", expanded=not bool(_load_events(owner_tid))):
        with st.form("sdx_event_create", clear_on_submit=True):
            title = st.text_input("Eventname", placeholder="z. B. Community Gaming Night", max_chars=100)
            game = st.text_input("Spiel / Kategorie", placeholder="z. B. Minecraft, Valorant, Just Chatting", max_chars=80)
            description = st.text_area("Beschreibung", max_chars=1500)
            event_date = st.text_input("Datum und Uhrzeit", placeholder="z. B. 15.11.2026, 19:00 Uhr", max_chars=80)
            capacity = st.number_input("Maximale Teilnehmerzahl (0 = unbegrenzt)", min_value=0, max_value=10000, value=24, step=1)
            platform = st.selectbox("Eventtyp", ["Community-Abend", "Turnier", "Watchparty", "Gemeinschaftsprojekt", "Sonstiges"])
            submitted = st.form_submit_button("Event erstellen", type="primary", use_container_width=True)
        if submitted:
            if not title.strip():
                st.error("Bitte gib dem Event einen Namen.")
            else:
                event_id = secrets.token_urlsafe(9).replace("-", "_")
                record = {
                    "title": title.strip(),
                    "game": game.strip(),
                    "description": description.strip(),
                    "event_date": event_date.strip(),
                    "capacity": int(capacity),
                    "event_type": platform,
                    "owner_tid": str(owner_tid),
                    "owner_name": str(twitch_username),
                    "status": "open",
                    "created_at": _now_label(),
                    "created_ts": int(datetime.now(TZ).timestamp() * 1000),
                    "participants": {},
                }
                try:
                    db.reference(f"{EVENTS_PATH}/{event_id}").set(record)
                    st.success("Event erstellt!")
                    st.code(f"?event={event_id}", language=None)
                    st.info("Öffne den Link deiner Streamlit-App mit diesem Parameter, um die öffentliche Eventseite aufzurufen.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Event konnte nicht gespeichert werden: {exc}")

    events = _load_events(owner_tid)
    if not events:
        st.info("Du hast noch keine Events erstellt.")
        return
    for event in events:
        event_id = event["id"]
        participants = _participant_list(event)
        cap = int(event.get("capacity") or 0)
        with st.container(border=True):
            left, right = st.columns([4, 1])
            with left:
                st.markdown(f"### {event.get('title', 'Event')}")
                st.caption(f"{event.get('event_type', 'Event')} · {event.get('game') or 'Keine Kategorie'} · {event.get('event_date') or 'Termin offen'}")
                st.write(event.get("description") or "Keine Beschreibung hinterlegt.")
                st.caption(f"Anmeldungen: {len(participants)}" + (f" / {cap}" if cap else " · unbegrenzt") + f" · Status: {event.get('status', 'open')}")
                st.code(f"?event={event_id}", language=None)
            with right:
                st.write("")
                if event.get("status") == "open":
                    if st.button("Anmeldung schließen", key=f"sdx_close_{event_id}", use_container_width=True):
                        _event_ref(event_id).update({"status": "closed"})
                        st.rerun()
                else:
                    if st.button("Wieder öffnen", key=f"sdx_open_{event_id}", use_container_width=True):
                        _event_ref(event_id).update({"status": "open"})
                        st.rerun()
                if st.button("Event löschen", key=f"sdx_delete_{event_id}", use_container_width=True):
                    st.session_state[f"sdx_confirm_delete_{event_id}"] = True
            if st.session_state.get(f"sdx_confirm_delete_{event_id}"):
                st.warning("Dieses Event samt Anmeldungen endgültig löschen?")
                c1, c2 = st.columns(2)
                if c1.button("Ja, löschen", key=f"sdx_yes_delete_{event_id}", type="primary"):
                    _event_ref(event_id).delete()
                    st.session_state.pop(f"sdx_confirm_delete_{event_id}", None)
                    st.rerun()
                if c2.button("Abbrechen", key=f"sdx_no_delete_{event_id}"):
                    st.session_state.pop(f"sdx_confirm_delete_{event_id}", None)
                    st.rerun()
            if participants:
                with st.expander(f"Teilnehmerliste ({len(participants)})"):
                    for p in participants:
                        cols = st.columns([3, 2, 1])
                        cols[0].write(p.get("display_name", "Unbekannt"))
                        cols[1].caption(p.get("platform", ""))
                        if cols[2].button("Entfernen", key=f"sdx_remove_{event_id}_{p['id']}"):
                            db.reference(f"{EVENTS_PATH}/{event_id}/participants/{p['id']}").delete()
                            st.rerun()


def render_public_events():
    st.title("🎉 StreamDex Events")
    st.caption("Community-Events entdecken und anmelden.")
    events = _load_events(include_closed=False)
    if not events:
        st.info("Aktuell sind keine offenen Events verfügbar.")
        return
    for event in events:
        event_id = event["id"]
        people = _participant_list(event)
        cap = int(event.get("capacity") or 0)
        with st.container(border=True):
            st.subheader(event.get("title", "Event"))
            st.caption(f"{event.get('event_type', 'Event')} · {event.get('game') or 'Community'} · {event.get('event_date') or 'Termin offen'}")
            st.write(event.get("description") or "Keine Beschreibung hinterlegt.")
            st.caption(f"Veranstalter: {event.get('owner_name', 'StreamDex')} · {len(people)} angemeldet" + (f" / {cap}" if cap else ""))
            with st.form(f"sdx_public_join_{event_id}"):
                name = st.text_input("Dein Anzeigename", max_chars=60, key=f"sdx_name_{event_id}")
                platform = st.selectbox("Plattform", ["Twitch", "Discord", "Web"], key=f"sdx_platform_{event_id}")
                submit = st.form_submit_button("Jetzt anmelden", type="primary", use_container_width=True)
            if submit:
                if event.get("status") != "open":
                    st.error("Die Anmeldung ist geschlossen.")
                elif not name.strip():
                    st.error("Bitte gib einen Anzeigenamen ein.")
                elif any(p.get("display_name", "").strip().casefold() == name.strip().casefold() for p in people):
                    st.warning("Dieser Anzeigename ist für dieses Event bereits angemeldet.")
                elif cap and len(people) >= cap:
                    st.error("Dieses Event ist bereits voll. Eine Warteliste ist in dieser ersten Version noch nicht verfügbar.")
                else:
                    try:
                        db.reference(f"{EVENTS_PATH}/{event_id}/participants").push({
                            "display_name": name.strip(),
                            "platform": platform,
                            "registered_at": _now_label(),
                            "registered_ts": int(datetime.now(TZ).timestamp() * 1000),
                        })
                        st.success("Du bist angemeldet!")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Anmeldung fehlgeschlagen: {exc}")


def render_public_event(event_id):
    ref = _event_ref(event_id)
    if ref is None:
        st.error("Der Event-Link ist ungültig.")
        return
    event = ref.get()
    if not isinstance(event, dict):
        st.error("Dieses Event wurde nicht gefunden.")
        return
    st.title(f"🎉 {event.get('title', 'StreamDex Event')}")
    st.caption(f"{event.get('event_type', 'Event')} · {event.get('game') or 'Community'} · {event.get('event_date') or 'Termin offen'}")
    st.write(event.get("description") or "Keine Beschreibung hinterlegt.")
    if event.get("status") != "open":
        st.warning("Die Anmeldung für dieses Event ist geschlossen.")
    people = _participant_list(event)
    cap = int(event.get("capacity") or 0)
    st.metric("Angemeldet", f"{len(people)}" + (f" / {cap}" if cap else ""))
    if event.get("status") == "open":
        with st.form(f"sdx_single_join_{event_id}"):
            name = st.text_input("Dein Anzeigename", max_chars=60)
            platform = st.selectbox("Plattform", ["Twitch", "Discord", "Web"])
            submit = st.form_submit_button("Jetzt anmelden", type="primary", use_container_width=True)
        if submit:
            if not name.strip():
                st.error("Bitte gib einen Anzeigenamen ein.")
            elif any(p.get("display_name", "").strip().casefold() == name.strip().casefold() for p in people):
                st.warning("Dieser Anzeigename ist bereits angemeldet.")
            elif cap and len(people) >= cap:
                st.error("Das Event ist voll. Eine Warteliste ist noch nicht verfügbar.")
            else:
                ref.child("participants").push({
                    "display_name": name.strip(),
                    "platform": platform,
                    "registered_at": _now_label(),
                    "registered_ts": int(datetime.now(TZ).timestamp() * 1000),
                })
                st.success("Du bist angemeldet!")
                st.rerun()
    st.subheader(f"Teilnehmer ({len(people)})")
    if people:
        for person in people:
            st.write(f"• {person.get('display_name', 'Unbekannt')} · {person.get('platform', '')}")
    else:
        st.caption("Noch keine Anmeldungen.")
