"""Persönlicher StreamDex Planner: Stream-Termine, Monatskalender und Erinnerungen."""
import calendar
import re
import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import streamlit as st
from firebase_admin import db

TZ = ZoneInfo("Europe/Berlin")
TID_RE = re.compile(r"^[0-9]{1,15}$")
ROOT = "streamdex_planner"


def _owner_ref(owner_tid):
    tid = str(owner_tid or "")
    if not TID_RE.fullmatch(tid):
        raise ValueError("Ungültige Twitch-ID.")
    return db.reference(f"{ROOT}/{tid}")


def _read_items(ref, key):
    data = ref.child(key).get() or {}
    if not isinstance(data, dict):
        return []
    return [{"id": str(item_id), **value} for item_id, value in data.items() if isinstance(value, dict)]


def _as_datetime(value):
    try:
        parsed = datetime.fromisoformat(str(value))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=TZ)
        return parsed.astimezone(TZ)
    except (TypeError, ValueError):
        return None


def _date_label(value):
    dt = _as_datetime(value)
    return dt.strftime("%d.%m.%Y · %H:%M Uhr") if dt else "Termin unbekannt"


def _save_stream(ref, stream):
    stream_id = uuid.uuid4().hex
    ref.child(f"streams/{stream_id}").set(stream)
    return stream_id


def _fmt_month(value):
    months = ("Januar", "Februar", "März", "April", "Mai", "Juni",
              "Juli", "August", "September", "Oktober", "November", "Dezember")
    return f"{months[value.month - 1]} {value.year}"


def _calendar_grid(owner_tid, streams):
    today = datetime.now(TZ).date()
    month_key = f"planner_month_{owner_tid}"
    selected_key = f"planner_selected_date_{owner_tid}"
    month = st.session_state.get(month_key)
    if not isinstance(month, date):
        month = today.replace(day=1)
    month = month.replace(day=1)
    st.session_state[month_key] = month

    prev_col, title_col, next_col = st.columns([1, 4, 1])
    with prev_col:
        if st.button("←", key=f"planner_prev_{owner_tid}", help="Vorheriger Monat", use_container_width=True):
            st.session_state[month_key] = (month - timedelta(days=1)).replace(day=1)
            st.rerun()
    with title_col:
        st.markdown(f"<div style='text-align:center;padding:7px;font-size:1.2rem;font-weight:750'>{_fmt_month(month)}</div>", unsafe_allow_html=True)
    with next_col:
        if st.button("→", key=f"planner_next_{owner_tid}", help="Nächster Monat", use_container_width=True):
            st.session_state[month_key] = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
            st.rerun()

    counts = {}
    for row in streams:
        start = _as_datetime(row.get("start_at"))
        if start:
            counts[start.date()] = counts.get(start.date(), 0) + 1

    header_cols = st.columns(7, gap="small")
    for col, label in zip(header_cols, ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")):
        col.markdown(f"<div style='text-align:center;color:#94a3b8;font-size:.78rem;font-weight:700'>{label}</div>", unsafe_allow_html=True)

    selected = st.session_state.get(selected_key)
    if not isinstance(selected, date) or selected.month != month.month or selected.year != month.year:
        selected = today if (today.month, today.year) == (month.month, month.year) else month
        st.session_state[selected_key] = selected

    for week in calendar.Calendar(firstweekday=0).monthdatescalendar(month.year, month.month):
        cols = st.columns(7, gap="small")
        for col, day in zip(cols, week):
            count = counts.get(day, 0)
            label = f"{'🟣 ' if count else ''}{day.day}" + (f" · {count}" if count else "")
            if day.month != month.month:
                label = f"· {day.day}"
            with col:
                if st.button(label, key=f"planner_day_{owner_tid}_{day.isoformat()}",
                             type="primary" if day == selected else "secondary",
                             use_container_width=True, help=f"{day.strftime('%d.%m.%Y')} · {count} Stream(s)"):
                    st.session_state[selected_key] = day
                    st.rerun()
    st.caption("🟣 Tage mit geplanten Streams · Zahl = Anzahl der Termine")
    return st.session_state[selected_key]


def _render_stream_form(ref, owner_tid, default_name):
    with st.form(f"planner_new_stream_{owner_tid}", clear_on_submit=True):
        st.markdown("#### Neuen Stream eintragen")
        title = st.text_input("Stream-Titel", placeholder="z. B. Community-Abend in Minecraft", max_chars=120)
        c1, c2 = st.columns(2)
        with c1:
            start_date = st.date_input("Datum", value=datetime.now(TZ).date() + timedelta(days=1), key=f"planner_date_{owner_tid}")
            start_time = st.time_input("Startzeit", value=time(19, 0), key=f"planner_time_{owner_tid}")
            category = st.text_input("Kategorie / Spiel", placeholder="Just Chatting, Minecraft …", max_chars=80)
        with c2:
            platform = st.selectbox("Plattform", ["Twitch", "YouTube", "TikTok", "Kick", "Sonstige"], key=f"planner_platform_{owner_tid}")
            reminder = st.selectbox("Erinnerung vor dem Start", options=[0, 10, 30, 60, 180, 1440],
                                    format_func=lambda n: "Keine" if n == 0 else ("24 Stunden" if n == 1440 else f"{n} Minuten"),
                                    index=2, key=f"planner_reminder_{owner_tid}")
            stream_url = st.text_input("Stream-Link (optional)", placeholder="https://www.twitch.tv/deinkanal", max_chars=300)
        notes = st.text_area("Notizen / Ankündigung", placeholder="Was möchtest du vorbereiten oder ankündigen?", max_chars=1200)
        submitted = st.form_submit_button("＋ Stream speichern", type="primary", use_container_width=True)
    if not submitted:
        return
    if not title.strip():
        st.error("Bitte gib deinem Stream einen Titel.")
        return
    now = datetime.now(TZ)
    if start_date < now.date() or (start_date == now.date() and start_time <= now.time().replace(tzinfo=None)):
        st.error("Der Starttermin muss in der Zukunft liegen.")
        return
    url = stream_url.strip()
    if url and not url.startswith("https://"):
        st.error("Der Stream-Link muss mit https:// beginnen.")
        return
    start_at = datetime.combine(start_date, start_time).replace(tzinfo=TZ)
    try:
        _save_stream(ref, {
            "title": title.strip(), "category": category.strip(), "platform": platform,
            "start_at": start_at.isoformat(), "stream_url": url, "notes": notes.strip(),
            "reminder_minutes": int(reminder), "reminder_dismissed": False, "status": "planned",
            "created_at": now.isoformat(), "owner_name": str(default_name or ""),
        })
        st.success("Stream wurde im Planner gespeichert.")
        st.rerun()
    except Exception:
        st.error("Der Stream konnte nicht gespeichert werden. Bitte prüfe die Firebase-Verbindung.")


def _render_stream_rows(ref, owner_tid, streams, selected_date=None):
    visible = []
    for row in streams:
        start = _as_datetime(row.get("start_at"))
        if start and (selected_date is None or start.date() == selected_date):
            visible.append((start, row))
    visible.sort(key=lambda item: item[0])
    if not visible:
        st.info("Für diesen Zeitraum sind keine Streams geplant.")
        return
    for start, row in visible:
        stream_id = row["id"]
        is_done = row.get("status") == "done"
        with st.container(border=True):
            info_col, action_col = st.columns([5, 1])
            with info_col:
                title = str(row.get("title", "Stream"))
                st.markdown(f"#### {'~~' + title + '~~' if is_done else title}")
                status = "✅ Erledigt" if is_done else "🟣 Geplant"
                st.caption(f"{start.strftime('%d.%m.%Y · %H:%M')} · {row.get('platform', 'Twitch')} · {row.get('category') or 'Keine Kategorie'} · {status}")
                if row.get("notes"):
                    st.write(row["notes"])
                if str(row.get("stream_url", "")).startswith("https://"):
                    st.link_button("🔗 Stream öffnen", row["stream_url"])
            with action_col:
                if not is_done and st.button("✓", key=f"planner_done_{owner_tid}_{stream_id}", help="Als erledigt markieren", use_container_width=True):
                    ref.child(f"streams/{stream_id}").update({"status": "done"})
                    st.rerun()
                if st.button("🗑", key=f"planner_delete_{owner_tid}_{stream_id}", help="Termin löschen", use_container_width=True):
                    st.session_state[f"planner_confirm_delete_{owner_tid}_{stream_id}"] = True
            confirm_key = f"planner_confirm_delete_{owner_tid}_{stream_id}"
            if st.session_state.get(confirm_key):
                st.warning("Diesen Stream-Termin endgültig löschen?")
                yes_col, no_col = st.columns(2)
                if yes_col.button("Ja, löschen", key=f"planner_confirm_yes_{owner_tid}_{stream_id}", type="primary"):
                    ref.child(f"streams/{stream_id}").delete()
                    st.session_state.pop(confirm_key, None)
                    st.rerun()
                if no_col.button("Abbrechen", key=f"planner_confirm_no_{owner_tid}_{stream_id}"):
                    st.session_state.pop(confirm_key, None)
                    st.rerun()


def _render_reminders(ref, owner_tid, streams):
    now = datetime.now(TZ)
    st.markdown("### 🔔 Deine Erinnerungen")
    st.caption("Stream-Erinnerungen werden zum eingestellten Zeitpunkt im Planner angezeigt. Für Browser-Push bei geschlossenem Dashboard wäre ein zusätzlicher Benachrichtigungsdienst nötig.")
    triggered, upcoming = [], []
    for row in streams:
        minutes = int(row.get("reminder_minutes") or 0)
        if row.get("status") == "done" or minutes <= 0 or row.get("reminder_dismissed"):
            continue
        start = _as_datetime(row.get("start_at"))
        if not start:
            continue
        remind_at = start - timedelta(minutes=minutes)
        item = (remind_at, start, row)
        if remind_at <= now <= start:
            triggered.append(item)
        elif remind_at > now:
            upcoming.append(item)

    for remind_at, start, row in sorted(triggered, key=lambda x: x[0]):
        st.warning(f"⏰ **Bald geht's los:** {row.get('title', 'Dein Stream')} · Start {start.strftime('%d.%m. um %H:%M Uhr')}")
        if st.button("Erinnerung ausblenden", key=f"planner_dismiss_{owner_tid}_{row['id']}"):
            ref.child(f"streams/{row['id']}").update({"reminder_dismissed": True})
            st.rerun()

    reminder_default = now + timedelta(hours=1)
    with st.form(f"planner_new_reminder_{owner_tid}", clear_on_submit=True):
        st.markdown("#### Persönliche Erinnerung hinzufügen")
        title = st.text_input("Was möchtest du nicht vergessen?", max_chars=120, placeholder="z. B. Thumbnail fertigstellen")
        due_date = st.date_input("Datum", value=reminder_default.date(), key=f"planner_rem_date_{owner_tid}")
        due_time = st.time_input("Uhrzeit", value=reminder_default.time().replace(second=0, microsecond=0), key=f"planner_rem_time_{owner_tid}")
        note = st.text_input("Notiz (optional)", max_chars=300)
        submit = st.form_submit_button("＋ Erinnerung speichern", type="primary", use_container_width=True)
    if submit:
        due = datetime.combine(due_date, due_time).replace(tzinfo=TZ)
        if not title.strip():
            st.error("Bitte gib der Erinnerung einen Titel.")
        elif due <= now:
            st.error("Der Erinnerungszeitpunkt muss in der Zukunft liegen.")
        else:
            reminder_id = uuid.uuid4().hex
            try:
                ref.child(f"reminders/{reminder_id}").set({"title": title.strip(), "note": note.strip(),
                    "due_at": due.isoformat(), "dismissed": False, "created_at": now.isoformat()})
                st.success("Erinnerung gespeichert.")
                st.rerun()
            except Exception:
                st.error("Die Erinnerung konnte nicht gespeichert werden. Bitte prüfe die Firebase-Verbindung.")

    reminders = _read_items(ref, "reminders")
    active = []
    for row in reminders:
        if row.get("dismissed"):
            continue
        due = _as_datetime(row.get("due_at"))
        if due:
            active.append((due, row))
    active.sort(key=lambda item: item[0])
    st.markdown("#### Persönliche Erinnerungen")
    if not active:
        st.info("Du hast keine offenen persönlichen Erinnerungen.")
    for due, row in active:
        with st.container(border=True):
            if due <= now:
                st.warning(f"⏰ **{row.get('title', 'Erinnerung')}** · fällig seit {_date_label(row.get('due_at'))}")
            else:
                st.markdown(f"**{row.get('title', 'Erinnerung')}**")
                st.caption(f"🔔 {_date_label(row.get('due_at'))}")
            if row.get("note"):
                st.write(row["note"])
            c1, c2 = st.columns(2)
            if c1.button("✓ Erledigt", key=f"planner_rem_done_{owner_tid}_{row['id']}", use_container_width=True):
                ref.child(f"reminders/{row['id']}").update({"dismissed": True})
                st.rerun()
            if c2.button("🗑 Löschen", key=f"planner_rem_delete_{owner_tid}_{row['id']}", use_container_width=True):
                ref.child(f"reminders/{row['id']}").delete()
                st.rerun()
    if upcoming:
        st.markdown("#### Kommende Stream-Erinnerungen")
        for remind_at, start, row in sorted(upcoming, key=lambda x: x[0])[:10]:
            st.caption(f"🔔 {_date_label(remind_at.isoformat())} · {row.get('title', 'Stream')} (Start: {start.strftime('%d.%m. um %H:%M')})")


def render_planner(owner_tid, twitch_username=""):
    """Rendert den Planner ausschließlich für die angemeldete Twitch-ID."""
    try:
        owner = _owner_ref(owner_tid)
        streams = _read_items(owner, "streams")
    except Exception:
        st.error("Der Planner ist gerade nicht erreichbar. Bitte prüfe die Firebase-Verbindung.")
        return

    st.markdown(
        "<div style='padding:22px 24px;margin:0 0 18px;border:1px solid rgba(139,92,246,.35);border-radius:20px;"
        "background:linear-gradient(120deg,rgba(30,27,75,.96),rgba(8,47,73,.88));'>"
        "<div style='color:#c4b5fd;font-weight:800;font-size:.72rem;letter-spacing:.13em'>STREAMDEX OS / CREATOR TOOLS</div>"
        "<h1 style='margin:.35rem 0;color:#fff'>▣ Stream Planner</h1>"
        "<p style='margin:0;color:#cbd5e1'>Plane deine Streams, behalte den Kalender im Blick und vergiss keine Vorbereitung.</p>"
        "</div>", unsafe_allow_html=True)
    st.caption(f"Angemeldet als **{twitch_username or 'Twitch-Streamer'}** · Alle Einträge sind an dein Twitch-Konto gebunden.")
    t_calendar, t_create, t_reminders = st.tabs(["📅 Kalender", "＋ Stream planen", "🔔 Erinnerungen"])
    with t_calendar:
        selected = _calendar_grid(owner_tid, streams)
        st.markdown(f"### 📆 {selected.strftime('%A, %d.%m.%Y')}")
        _render_stream_rows(owner, owner_tid, streams, selected)
        st.divider()
        st.markdown("#### Nächste Streams")
        now = datetime.now(TZ)
        next_streams = [s for s in streams if _as_datetime(s.get("start_at")) and _as_datetime(s.get("start_at")) >= now and s.get("status") != "done"]
        next_streams.sort(key=lambda s: _as_datetime(s.get("start_at")))
        _render_stream_rows(owner, owner_tid, next_streams[:8])
    with t_create:
        _render_stream_form(owner, owner_tid, twitch_username)
        st.divider()
        st.markdown("#### Deine geplanten Streams")
        _render_stream_rows(owner, owner_tid, streams)
    with t_reminders:
        _render_reminders(owner, owner_tid, streams)
