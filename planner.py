"""Persönlicher StreamDex Planner: Stream-Termine, Monatskalender und Erinnerungen."""
import calendar
import json
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import streamlit as st
from firebase_admin import db
from streamdex_security import has_active_user_session
from radar import _app_token, _creator_access_token, _credentials, _helix_get

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
            duration = st.selectbox("Streamdauer", [30, 45, 60, 90, 120, 180, 240], index=4, format_func=lambda n: f"{n} Minuten", key=f"planner_duration_{owner_tid}")
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
            "start_at": start_at.isoformat(), "duration_minutes": int(duration), "stream_url": url, "notes": notes.strip(),
            "reminder_minutes": int(reminder), "reminder_dismissed": False, "status": "planned",
            "created_at": now.isoformat(), "owner_name": str(default_name or ""),
        })
        st.success("Stream wurde im Planner gespeichert.")
        st.rerun()
    except Exception:
        st.error("Der Stream konnte nicht gespeichert werden. Bitte prüfe die Firebase-Verbindung.")


def _render_stream_rows(ref, owner_tid, streams, selected_date=None, view_key="list"):
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
                    st.link_button("🔗 Stream öffnen", row["stream_url"], key=f"planner_link_{owner_tid}_{view_key}_{stream_id}")
            with action_col:
                if not is_done and st.button("✓", key=f"planner_done_{owner_tid}_{view_key}_{stream_id}", help="Als erledigt markieren", use_container_width=True):
                    ref.child(f"streams/{stream_id}").update({"status": "done"})
                    st.rerun()
                if st.button("🗑", key=f"planner_delete_{owner_tid}_{view_key}_{stream_id}", help="Termin löschen", use_container_width=True):
                    st.session_state[f"planner_confirm_delete_{owner_tid}_{stream_id}"] = True
            confirm_key = f"planner_confirm_delete_{owner_tid}_{view_key}_{stream_id}"
            if st.session_state.get(confirm_key):
                st.warning("Diesen Stream-Termin endgültig löschen?")
                yes_col, no_col = st.columns(2)
                if yes_col.button("Ja, löschen", key=f"planner_confirm_yes_{owner_tid}_{view_key}_{stream_id}", type="primary"):
                    ref.child(f"streams/{stream_id}").delete()
                    st.session_state.pop(confirm_key, None)
                    st.rerun()
                if no_col.button("Abbrechen", key=f"planner_confirm_no_{owner_tid}_{view_key}_{stream_id}"):
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



def _load_twitch_schedule(owner_tid):
    """Read the channel's public Twitch schedule with an app access token."""
    client_id, client_secret = _credentials()
    token = _app_token(client_id, client_secret)
    start_time = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat().replace("+00:00", "Z")
    try:
        result = _helix_get("schedule", token, {
            "broadcaster_id": str(owner_tid),
            "first": 50,
            "start_time": start_time,
        })
    except RuntimeError as exc:
        if "HTTP 404" in str(exc):
            return []
        raise
    data = result.get("data", {})
    segments = data.get("segments", []) if isinstance(data, dict) else []
    return [segment for segment in segments if isinstance(segment, dict)]


def _publish_planner_stream_to_twitch(owner_tid, stream):
    """Publish a single planned appointment to Twitch; requires explicit schedule permission."""
    token = _creator_access_token(str(owner_tid))
    if not token:
        raise RuntimeError("Bitte melde dich erneut über Twitch an und bestätige die Zeitplan-Berechtigung.")
    scopes = st.session_state.get("twitch_oauth_scopes", [])
    if "channel:manage:schedule" not in scopes:
        raise RuntimeError("Deine aktuelle Twitch-Freigabe enthält noch keine Zeitplan-Berechtigung. Verbinde Twitch bitte erneut.")
    start = _as_datetime(stream.get("start_at"))
    if not start or start <= datetime.now(TZ):
        raise RuntimeError("Nur zukünftige Stream-Termine können veröffentlicht werden.")
    client_id, _ = _credentials()
    params = urllib.parse.urlencode({"broadcaster_id": str(owner_tid)})
    url = "https://api.twitch.tv/helix/schedule/segment?" + params
    body = {
        "start_time": start.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "duration": max(15, min(720, int(stream.get("duration_minutes") or 120))),
        "timezone": "Europe/Berlin",
        "title": str(stream.get("title") or "StreamDex Stream")[:140],
        "is_recurring": False,
    }
    category = str(stream.get("category") or "").strip()
    if category:
        try:
            search = _helix_get("search/categories", token, {"query": category, "first": 1})
            matches = search.get("data", [])
            if matches and isinstance(matches[0], dict) and matches[0].get("id"):
                body["category_id"] = str(matches[0]["id"])
        except Exception:
            pass
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Client-Id": client_id,
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise RuntimeError("Twitch hat die Veröffentlichung abgelehnt. Prüfe die Zeitplan-Berechtigung und verbinde Twitch erneut.") from None
        if exc.code in (400, 409, 422):
            raise RuntimeError("Twitch konnte den Termin nicht übernehmen. Einmalige Termine sind je nach Affiliate-/Partnerstatus eingeschränkt oder überschneiden sich mit dem Twitch-Zeitplan.") from None
        raise RuntimeError(f"Twitch-Zeitplan ist gerade nicht erreichbar (HTTP {exc.code}).") from None
    except (urllib.error.URLError, TimeoutError):
        raise RuntimeError("Twitch-Zeitplan ist gerade nicht erreichbar. Bitte erneut versuchen.") from None
    try:
        result = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        result = {}
    data = result.get("data", {}) if isinstance(result, dict) else {}
    segments = data.get("segments", []) if isinstance(data, dict) else []
    segment_id = str(segments[0].get("id") or "") if segments and isinstance(segments[0], dict) else ""
    return segment_id


def _render_twitch_schedule_integration(ref, owner_tid, streams, twitch_username, reauth_url=None):
    st.markdown("### 🟣 Twitch-Zeitplan")
    st.caption("Importiere kommende Termine von Twitch in deinen StreamDex Planner oder veröffentliche lokale Pläne direkt bei Twitch. Einmalige Twitch-Termine können je nach Affiliate-/Partnerstatus eingeschränkt sein; Änderungen erfolgen erst nach Klick auf die jeweilige Aktion.")
    if st.button("🔄 Twitch-Zeitplan aktualisieren", key=f"planner_twitch_refresh_{owner_tid}"):
        _load_twitch_schedule.clear()
        st.rerun()
    try:
        with st.spinner("Twitch-Zeitplan wird geladen …"):
            segments = _load_twitch_schedule(str(owner_tid))
    except Exception:
        segments = []
        st.warning("Der Twitch-Zeitplan konnte gerade nicht geladen werden. Prüfe die Twitch-API-Zugangsdaten und versuche es erneut.")

    imported_ids = {str(item.get("twitch_schedule_id") or "") for item in streams if item.get("twitch_schedule_id")}
    if not segments:
        st.info("Twitch hat aktuell keine kommenden Termine zurückgegeben. Du kannst unten trotzdem einen lokalen Plan an Twitch senden.")
    else:
        st.markdown("#### Termine von Twitch importieren")
        for index, segment in enumerate(segments[:50]):
            segment_id = str(segment.get("id") or "")
            start = _as_datetime(segment.get("start_time"))
            end = _as_datetime(segment.get("end_time"))
            title = str(segment.get("title") or "Twitch-Stream")
            category = segment.get("category")
            if isinstance(category, dict):
                category_name = str(category.get("name") or "")
            else:
                category_name = ""
            with st.container(border=True):
                left, right = st.columns([4, 1])
                left.markdown(f"**{title}**")
                left.caption(
                    f"{start.strftime('%d.%m.%Y · %H:%M') if start else 'Termin unbekannt'}"
                    + (f"–{end.strftime('%H:%M')}" if end else "")
                    + f" · {category_name or 'Keine Kategorie'}"
                    + (" · Wiederkehrend" if segment.get("is_recurring") else "")
                )
                if segment.get("canceled_until"):
                    left.caption("Dieser Termin wurde bei Twitch abgesagt.")
                if segment_id and segment_id in imported_ids:
                    right.button("✓ Importiert", key=f"planner_twitch_imported_{owner_tid}_{index}", disabled=True, use_container_width=True)
                elif right.button("⬇ Importieren", key=f"planner_twitch_import_{owner_tid}_{index}", type="primary", use_container_width=True):
                    if not start:
                        st.error("Twitch hat keinen gültigen Startzeitpunkt geliefert.")
                    else:
                        duration = max(15, min(720, int((end - start).total_seconds() / 60))) if end else 120
                        _save_stream(ref, {
                            "title": title[:120],
                            "category": category_name[:80],
                            "platform": "Twitch",
                            "start_at": start.isoformat(),
                            "duration_minutes": duration,
                            "stream_url": f"https://www.twitch.tv/{urllib.parse.quote(str(twitch_username or ''))}" if twitch_username else "",
                            "notes": "Aus dem Twitch-Zeitplan importiert.",
                            "reminder_minutes": 30,
                            "reminder_dismissed": False,
                            "status": "planned",
                            "created_at": datetime.now(TZ).isoformat(),
                            "owner_name": str(twitch_username or ""),
                            "external_source": "twitch",
                            "twitch_schedule_id": segment_id,
                        })
                        st.success("Twitch-Termin wurde in deinen StreamDex Planner importiert.")
                        st.rerun()

    st.divider()
    st.markdown("#### StreamDex-Pläne an Twitch senden")
    now = datetime.now(TZ)
    pending = [
        item for item in streams
        if item.get("platform", "Twitch") == "Twitch"
        and item.get("status") != "done"
        and not item.get("twitch_schedule_id")
        and not item.get("published_to_twitch")
        and _as_datetime(item.get("start_at"))
        and _as_datetime(item.get("start_at")) > now
    ]
    if not pending:
        st.caption("Aktuell gibt es keine zukünftigen, noch nicht veröffentlichten Twitch-Pläne.")
    for index, item in enumerate(sorted(pending, key=lambda x: _as_datetime(x.get("start_at")))[:20]):
        start = _as_datetime(item.get("start_at"))
        with st.container(border=True):
            a, b = st.columns([4, 1])
            a.markdown(f"**{item.get('title') or 'Stream'}**")
            a.caption(f"{start.strftime('%d.%m.%Y · %H:%M') if start else 'Termin unbekannt'} · {item.get('category') or 'Keine Kategorie'} · {int(item.get('duration_minutes') or 120)} Minuten")
            if b.button("Bei Twitch veröffentlichen", key=f"planner_publish_twitch_{owner_tid}_{item['id']}", use_container_width=True):
                try:
                    segment_id = _publish_planner_stream_to_twitch(owner_tid, item)
                    ref.child(f"streams/{item['id']}").update({
                        "published_to_twitch": True,
                        "twitch_schedule_id": segment_id,
                        "twitch_published_at": datetime.now(TZ).isoformat(),
                    })
                    st.success("Dein Plan wurde bei Twitch eingetragen.")
                    st.rerun()
                except Exception as exc:
                    print(f"[planner] Twitch schedule publish failed: {type(exc).__name__}")
                    st.error("Twitch konnte den Termin nicht veröffentlichen. Prüfe die Verbindung und Berechtigungen.")
    granted_scopes = st.session_state.get("twitch_oauth_scopes", [])
    if reauth_url and "channel:manage:schedule" not in granted_scopes:
        st.caption("Für die Veröffentlichung braucht StreamDex die separate Twitch-Berechtigung „channel:manage:schedule“.")
        st.link_button("🟣 Twitch-Zeitplan-Berechtigung erneuern", reauth_url)


def render_planner(owner_tid, twitch_username="", reauth_url=None):
    """Rendert den Planner ausschließlich für die angemeldete Twitch-ID."""
    if not has_active_user_session(st.session_state, owner_tid):
        st.error("Für den Planner ist eine gültige Sitzung des Kontoinhabers erforderlich.")
        return
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
    t_calendar, t_create, t_reminders, t_twitch = st.tabs(["📅 Kalender", "＋ Stream planen", "🔔 Erinnerungen", "🟣 Twitch-Zeitplan"])
    with t_calendar:
        selected = _calendar_grid(owner_tid, streams)
        st.markdown(f"### 📆 {selected.strftime('%A, %d.%m.%Y')}")
        _render_stream_rows(owner, owner_tid, streams, selected, view_key="selected_day")
        st.divider()
        st.markdown("#### Nächste Streams")
        now = datetime.now(TZ)
        next_streams = [s for s in streams if _as_datetime(s.get("start_at")) and _as_datetime(s.get("start_at")) >= now and s.get("status") != "done"]
        next_streams.sort(key=lambda s: _as_datetime(s.get("start_at")))
        _render_stream_rows(owner, owner_tid, next_streams[:8], view_key="upcoming")
    with t_create:
        _render_stream_form(owner, owner_tid, twitch_username)
        st.divider()
        st.markdown("#### Deine geplanten Streams")
        _render_stream_rows(owner, owner_tid, streams, view_key="all_planned")
    with t_reminders:
        _render_reminders(owner, owner_tid, streams)
    with t_twitch:
        _render_twitch_schedule_integration(owner, owner_tid, streams, twitch_username, reauth_url)
