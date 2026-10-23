"""StreamDex Legacy – persönliche Community-Chronik und Aktivitätsverlauf."""
import csv
import io
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import streamlit as st
from firebase_admin import db

TZ = ZoneInfo("Europe/Berlin")
LABELS = {
    "giveaways": "Giveaways",
    "giveaway_participants": "Giveaway-Teilnahmen",
    "viewers": "Viewer",
    "checkins": "Check-ins",
    "slot_spins": "Slot-Spins",
    "megaslot_spins": "Mega-Slot-Spins",
    "raids": "Raids",
    "fish_catches": "Fänge",
    "harvests": "Ernten",
}


def _read(path):
    try:
        value = db.reference(path).get() or {}
        if isinstance(value, list):
            return {str(index): row for index, row in enumerate(value) if row is not None}
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _timestamp(value):
    try:
        if isinstance(value, (int, float)):
            n = float(value)
            if n > 10_000_000_000:
                n /= 1000
            return datetime.fromtimestamp(n, TZ)
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=TZ)
        return parsed.astimezone(TZ)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _entry(items, when, kind, title, details="", link=""):
    dt = _timestamp(when)
    if not dt:
        return
    items.append({
        "timestamp": dt.timestamp(),
        "Datum": dt.strftime("%d.%m.%Y · %H:%M"),
        "Typ": kind,
        "Ereignis": str(title or "")[:180],
        "Details": str(details or "")[:400],
        "Link": str(link or ""),
    })


def _timeline(tid):
    items = []
    history = _read(f"stats_history/{tid}")
    previous = None
    for day in sorted(history):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(day)):
            continue
        row = history.get(day)
        if not isinstance(row, dict):
            continue
        changes = []
        for key, label in LABELS.items():
            try:
                value = int(row.get(key) or 0)
                old_value = int((previous or {}).get(key) or 0)
            except (TypeError, ValueError):
                continue
            delta = value - old_value
            if previous is not None and delta > 0:
                changes.append(f"+{delta} {label}")
        if previous is None or changes:
            _entry(items, f"{day}T23:59:00", "Statistik", "Täglicher StreamDex-Community-Stand",
                   " · ".join(changes) if changes else "Erster gespeicherter Tagesstand")
        previous = row

    giveaway_log = _read(f"giveaway_log/{tid}")
    for row in giveaway_log.values():
        if not isinstance(row, dict):
            continue
        _entry(items, row.get("date"), "Giveaway", f"Giveaway: {row.get('prize') or 'Ohne Preisangabe'}",
               f"{row.get('participants', 0)} Teilnahmen")

    analytics = _read(f"radar_analytics/{tid}/sessions")
    for stream_id, row in analytics.items():
        if not isinstance(row, dict):
            continue
        started = row.get("started_at_unix")
        samples = row.get("samples") or {}
        viewers = []
        if isinstance(samples, dict):
            for sample in samples.values():
                if isinstance(sample, dict):
                    try:
                        viewers.append(int(sample.get("viewers") or 0))
                    except (TypeError, ValueError):
                        pass
        detail = str(row.get("game") or "Kategorie nicht angegeben")
        if viewers:
            detail += f" · Ø {round(sum(viewers) / len(viewers))} gemessene Zuschauer · Peak {max(viewers)}"
        _entry(items, started, "Stream", row.get("title") or "StreamDex-Stream",
               detail + f" · {len(viewers)} Messpunkte")

    planner = _read(f"streamdex_planner/{tid}/streams")
    for row in planner.values():
        if not isinstance(row, dict):
            continue
        start_at = row.get("start_at")
        status = "Erledigt" if row.get("status") == "done" else "Geplant"
        _entry(items, start_at or row.get("created_at"), "Planner",
               f"Streamplan: {row.get('title') or 'Stream'}",
               f"{status} · {row.get('platform') or 'Twitch'} · {row.get('category') or 'Keine Kategorie'}")

    events = _read("streamdex_events")
    for event_id, event in events.items():
        if not isinstance(event, dict):
            continue
        owned = str(event.get("owner_tid") or "") == str(tid)
        # Gemeinsame Chronik zeigt nur offene Events anderer Creator; eigene Events bleiben vollständig sichtbar.
        if not owned and event.get("status") != "open":
            continue
        people = event.get("participants") or {}
        count = len(people) if isinstance(people, dict) else 0
        event_kind = "Event" if owned else "Community"
        event_title = f"Dein Event: {event.get('title') or 'Event'}" if owned else f"Community-Event: {event.get('title') or 'Event'}"
        details = f"{count} Anmeldungen · {event.get('event_type') or 'Community-Event'} · {event.get('game') or 'Community'}"
        if not owned and event.get("owner_name"):
            details += f" · Veranstalter: {event.get('owner_name')}"
        _entry(items, event.get("created_ts") or event.get("created_at"), event_kind,
               event_title, details, f"https://streamdex.streamlit.app/?event={event_id}")

    polls = _read("community_polls")
    for poll in sorted(polls.values(), key=lambda row: int(row.get("created_at") or 0) if isinstance(row, dict) and str(row.get("created_at") or "").isdigit() else 0, reverse=True)[:50]:
        if not isinstance(poll, dict):
            continue
        votes = poll.get("votes") or {}
        vote_count = len(votes) if isinstance(votes, dict) else 0
        options = poll.get("options") or []
        option_count = len(options) if isinstance(options, (dict, list)) else 0
        status = "Geschlossen" if poll.get("closed") else "Offen"
        _entry(items, poll.get("created_at"), "Umfrage",
               f"Community-Umfrage: {poll.get('question') or 'Umfrage'}",
               f"{status} · {option_count} Antwortmöglichkeiten · {vote_count} Stimmen · {poll.get('created_by_name') or 'Community'}",
               "https://streamdex.streamlit.app/?feedback=1")

    try:
        public_suggestions = db.reference("feedback_inbox").order_by_child("ts").limit_to_last(100).get() or {}
    except Exception:
        public_suggestions = {}
    if isinstance(public_suggestions, dict):
        for suggestion in public_suggestions.values():
            if not isinstance(suggestion, dict) or not suggestion.get("community_visible"):
                continue
            _entry(items, suggestion.get("ts"), "Community-Idee",
                   f"Community-Idee: {suggestion.get('title') or 'Vorschlag'}",
                   f"{suggestion.get('category') or 'Allgemein'} · {suggestion.get('author_name') or 'Community'} · {suggestion.get('status') or 'neu'}",
                   "https://streamdex.streamlit.app/?feedback=1")

    clips = _read(f"streamdex_clips/{tid}")
    for clip in clips.values():
        if not isinstance(clip, dict):
            continue
        _entry(items, clip.get("imported_at"), "Clip", f"Clip importiert: {clip.get('title') or 'Twitch-Clip'}",
               f"{clip.get('creator_name') or 'Twitch'} · {clip.get('view_count', 0)} Aufrufe", str(clip.get("url") or ""))

    profile = _read(f"creator_profiles/{tid}")
    if profile and profile.get("updated_at"):
        _entry(items, profile.get("updated_at"), "Profil", "Creator-Profil aktualisiert",
               "Veröffentlicht" if profile.get("published") else "Privates Profil")

    return sorted(items, key=lambda item: item["timestamp"], reverse=True)


def render_legacy(tid, username=""):
    """Render the account-scoped history assembled from StreamDex's existing records."""
    st.markdown(
        "<div style='padding:24px;margin:0 0 18px;border:1px solid rgba(139,92,246,.3);border-radius:20px;"
        "background:linear-gradient(120deg,rgba(30,27,75,.96),rgba(8,47,73,.88));'>"
        "<div style='color:#c4b5fd;font-weight:800;font-size:.72rem;letter-spacing:.13em'>STREAMDEX OS / LEGACY</div>"
        "<h1 style='margin:.4rem 0;color:#fff'>📜 Community-Chronik</h1>"
        "<p style='margin:0;color:#cbd5e1'>Dein persönlicher Verlauf aus StreamDex-Statistiken, Streams, Planner-Terminen, Events und Giveaways.</p>"
        "</div>", unsafe_allow_html=True
    )
    st.caption(f"Private Chronik für {username or 'dein StreamDex-Konto'}. Es werden vorhandene gespeicherte Daten verwendet; alte Ereignisse werden nicht nachträglich erfunden.")
    try:
        items = _timeline(str(tid))
    except Exception:
        st.error("Die Chronik konnte gerade nicht erstellt werden.")
        return

    if not items:
        st.info("Deine Chronik beginnt, sobald StreamDex die ersten Tagesstände, Streams, Planungen oder Community-Events gespeichert hat.")
        return

    types = sorted({row["Typ"] for row in items})
    f1, f2 = st.columns([2, 3])
    selected_types = f1.multiselect("Ereignistypen", types, default=types, key=f"legacy_types_{tid}")
    query = f2.text_input("Chronik durchsuchen", placeholder="Streamtitel, Spiel, Event, Giveaway …", key=f"legacy_search_{tid}")
    shown = [
        row for row in items
        if row["Typ"] in selected_types
        and (not query or query.casefold() in " ".join(str(row.get(k, "")) for k in ("Typ", "Ereignis", "Details")).casefold())
    ]
    days_30 = sum(1 for row in items if row["timestamp"] >= (datetime.now(TZ) - timedelta(days=30)).timestamp())
    m1, m2, m3 = st.columns(3)
    m1.metric("Einträge gesamt", len(items))
    m2.metric("Letzte 30 Tage", days_30)
    m3.metric("Verschiedene Bereiche", len(types))
    if not shown:
        st.info("Zu diesem Filter wurden keine Chronik-Einträge gefunden.")
        return

    daily_counts = {}
    for row in shown:
        day = datetime.fromtimestamp(row["timestamp"], TZ).strftime("%d.%m.")
        daily_counts[day] = daily_counts.get(day, 0) + 1
    if len(daily_counts) > 1:
        chart_rows = list(reversed(list(daily_counts.items())[:30]))
        st.bar_chart({ "Ereignisse": {day: count for day, count in chart_rows} }, height=180)

    st.markdown(f"### 🗂️ Chronik ({len(shown)} Einträge)")
    for index, row in enumerate(shown[:200]):
        with st.container(border=True):
            left, right = st.columns([5, 1])
            left.markdown(f"**{row['Ereignis']}**")
            left.caption(f"{row['Datum']} · {row['Typ']}")
            if row["Details"]:
                left.write(row["Details"])
            if row["Link"].startswith("https://"):
                right.link_button("Öffnen", row["Link"], key=f"legacy_link_{tid}_{index}", use_container_width=True)

    if len(shown) > 200:
        st.caption("Es werden die 200 neuesten gefilterten Einträge angezeigt. Der Export enthält alle gefilterten Einträge.")
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["Datum", "Typ", "Ereignis", "Details", "Link"], delimiter=";")
    writer.writeheader()
    writer.writerows([{key: row[key] for key in writer.fieldnames} for row in shown])
    st.download_button("⬇️ Chronik als CSV exportieren", output.getvalue().encode("utf-8-sig"),
                       file_name="streamdex_community_chronik.csv", mime="text/csv", key=f"legacy_export_{tid}")
