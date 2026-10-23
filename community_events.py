"""StreamDex Community & Events – Überblick und Verbindung der vorhandenen Community-Tools."""
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st
from firebase_admin import db

TZ = ZoneInfo("Europe/Berlin")
PUBLIC_BASE = "https://streamdex.streamlit.app/"


def _read_dict(path):
    try:
        value = db.reference(path).get() or {}
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def render_community_integrations(tid, username=""):
    st.markdown(
        "<div style='padding:24px;margin:0 0 18px;border:1px solid rgba(139,92,246,.3);border-radius:20px;"
        "background:linear-gradient(120deg,rgba(30,27,75,.96),rgba(8,47,73,.88));'>"
        "<div style='color:#c4b5fd;font-weight:800;font-size:.72rem;letter-spacing:.13em'>STREAMDEX OS / COMMUNITY HUB</div>"
        "<h1 style='margin:.4rem 0;color:#fff'>🤝 Community & Events</h1>"
        "<p style='margin:0;color:#cbd5e1'>Verbinde deine Stream-Pläne, Community-Events, Umfragen und dein öffentliches Creator-Profil.</p>"
        "</div>", unsafe_allow_html=True
    )
    events = _read_dict("streamdex_events")
    all_events = [(event_id, event) for event_id, event in events.items() if isinstance(event, dict)]
    own_events = [(event_id, event) for event_id, event in all_events if str(event.get("owner_tid") or "") == str(tid)]
    open_events = [(event_id, event) for event_id, event in all_events if event.get("status") == "open"]
    polls = _read_dict("community_polls")
    feedback = _read_dict("feedback_inbox")
    my_suggestions = [item for item in feedback.values() if isinstance(item, dict) and str(item.get("tid") or "") == str(tid)]
    registrations = sum(len(event.get("participants") or {}) for _, event in own_events if isinstance(event.get("participants") or {}, dict))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🎉 Deine Events", len(own_events))
    c2.metric("👥 Anmeldungen", registrations)
    c3.metric("🌐 Offene Community-Events", len(open_events))
    c4.metric("🗳️ Community-Umfragen", len(polls))
    st.caption(f"StreamDex-Konto: {username or tid} · {len(my_suggestions)} Feedback-/Vorschlags-Einträge gehören zu deinem Konto.")

    st.markdown("### 🔗 Verbundene Community-Bereiche")
    b1, b2, b3 = st.columns(3)
    b1.link_button("🌐 Öffentliche Event-Übersicht", PUBLIC_BASE + "?events=1", use_container_width=True)
    b2.link_button("💬 Feedback & Umfragen", PUBLIC_BASE + "?feedback=1", use_container_width=True)
    b3.link_button("▣ Stream Planner", PUBLIC_BASE + "?planner=1", use_container_width=True)

    st.markdown("### 📣 Offene Events aus der StreamDex-Community")
    if not open_events:
        st.info("Derzeit sind keine offenen Community-Events veröffentlicht.")
    else:
        open_events.sort(key=lambda pair: int(pair[1].get("created_ts") or 0), reverse=True)
        for event_id, event in open_events[:12]:
            participants = event.get("participants") or {}
            count = len(participants) if isinstance(participants, dict) else 0
            capacity = int(event.get("capacity") or 0)
            with st.container(border=True):
                ctext, caction = st.columns([4, 1])
                ctext.markdown(f"#### {event.get('title') or 'Community-Event'}")
                ctext.caption(f"{event.get('event_type') or 'Community-Event'} · {event.get('game') or 'Community'} · {event.get('event_date') or 'Termin offen'}")
                ctext.write(event.get("description") or "Keine Beschreibung hinterlegt.")
                ctext.caption(f"Veranstalter: {event.get('owner_name') or 'StreamDex'} · {count} Anmeldungen" + (f" / {capacity}" if capacity else ""))
                caction.link_button("Event ansehen", PUBLIC_BASE + "?event=" + str(event_id), key=f"community_event_open_{event_id}", use_container_width=True)

    st.markdown("### 🧩 Zusammenspiel mit deinem Creator-Profil")
    profile = _read_dict(f"creator_profiles/{tid}")
    if isinstance(profile, dict) and profile.get("published") and profile.get("slug"):
        profile_url = PUBLIC_BASE + "?profile=" + str(profile["slug"])
        st.success("Dein Creator-Profil ist öffentlich. Du kannst es als zentrale Anlaufstelle für Socials, Streams und Community-Events verwenden.")
        st.link_button("♙ Öffentliches Creator-Profil öffnen", profile_url, use_container_width=True)
    else:
        st.info("Veröffentliche dein Creator-Profil im Tab „Profil“, damit die Community eine zentrale Seite mit deinen Links und dem Live-Status findet.")
