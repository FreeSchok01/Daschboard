"""StreamDex Radar: persönliche Twitch-Watchlist mit Live-Status und StreamDex-Statistiken."""
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import streamlit as st
from firebase_admin import db

TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
TWITCH_USERS_URL = "https://api.twitch.tv/helix/users"
TWITCH_STREAMS_URL = "https://api.twitch.tv/helix/streams"
TWITCH_VALIDATE_URL = "https://id.twitch.tv/oauth2/validate"
TWITCH_API_BASE = "https://api.twitch.tv/helix"
MAX_WATCHLIST = 50
LOGIN_RE = re.compile(r"^[a-z0-9_]{1,25}$")

STAT_LABELS = {
    "giveaways": "Giveaways",
    "giveaway_participants": "Giveaway-Teilnahmen",
    "viewers": "Viewer erfasst",
    "checkins": "Check-ins",
    "slot_spins": "Slot-Spins",
    "megaslot_spins": "Mega-Slot-Spins",
    "fish_catches": "Fänge",
    "harvests": "Ernten",
    "raids": "Raids",
}


def _credentials():
    for section in (
        st.secrets.get("twitch", {}),
        (st.secrets.get("auth", {}) or {}).get("twitch", {}),
    ):
        if hasattr(section, "get"):
            client_id = str(section.get("client_id", "") or "").strip()
            client_secret = str(section.get("client_secret", "") or "").strip()
            if client_id and client_secret:
                return client_id, client_secret
    raise RuntimeError(
        "Die Twitch-API ist noch nicht konfiguriert. Prüfe die vorhandenen Twitch-Zugangsdaten in Streamlit Secrets."
    )


def _http_json(url, method="GET", form=None, headers=None):
    data = urllib.parse.urlencode(form).encode("utf-8") if form else None
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # Niemals Request-Header oder Tokens in Fehlermeldungen ausgeben.
        if exc.code in (401, 403):
            raise RuntimeError("Twitch hat die Radar-Anfrage abgelehnt. Bitte die Twitch-Zugangsdaten prüfen.") from None
        if exc.code == 429:
            raise RuntimeError("Twitch begrenzt gerade die Anfragen. Bitte in einer Minute erneut versuchen.") from None
        raise RuntimeError(f"Twitch ist gerade nicht erreichbar (HTTP {exc.code}).") from None
    except (urllib.error.URLError, TimeoutError):
        raise RuntimeError("Twitch ist gerade nicht erreichbar. Bitte Verbindung prüfen und erneut versuchen.") from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RuntimeError("Twitch hat eine ungültige Antwort zurückgegeben.") from None


@st.cache_data(ttl=3300, show_spinner=False)
def _app_token(client_id, client_secret):
    result = _http_json(
        TWITCH_TOKEN_URL,
        method="POST",
        form={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    token = str(result.get("access_token", "") or "")
    if not token:
        raise RuntimeError("Twitch hat kein API-Zugriffstoken zurückgegeben.")
    return token


def _normalize_login(value):
    value = str(value or "").strip()
    if "://" not in value and ("twitch.tv/" in value.lower()):
        value = "https://" + value
    if "://" in value:
        parsed = urllib.parse.urlparse(value)
        value = parsed.path.strip("/").split("/")[0]
    elif "/" in value:
        value = value.strip("/").split("/")[0]
    value = value.lstrip("@").lower()
    if not LOGIN_RE.fullmatch(value):
        return None
    return value


def _load_watchlist(tid):
    raw = db.reference(f"radar_watchlists/{tid}").get() or {}
    if isinstance(raw, dict):
        names = raw.get("names", [])
    elif isinstance(raw, list):
        names = raw
    else:
        names = []
    if not isinstance(names, list):
        return []
    result = []
    for name in names[:MAX_WATCHLIST]:
        normalized = _normalize_login(name)
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def _save_watchlist(tid, names):
    cleaned = []
    for name in names:
        normalized = _normalize_login(name)
        if normalized and normalized not in cleaned:
            cleaned.append(normalized)
    db.reference(f"radar_watchlists/{tid}").set({
        "names": cleaned[:MAX_WATCHLIST],
        "updated_at": {".sv": "timestamp"},
    })
    return cleaned[:MAX_WATCHLIST]


@st.cache_data(ttl=45, show_spinner=False)
def _fetch_channels(logins_tuple):
    logins = list(logins_tuple)
    if not logins:
        return []
    client_id, client_secret = _credentials()
    token = _app_token(client_id, client_secret)
    headers = {"Client-Id": client_id, "Authorization": f"Bearer {token}"}
    users_url = TWITCH_USERS_URL + "?" + urllib.parse.urlencode([("login", name) for name in logins])
    user_rows = _http_json(users_url, headers=headers).get("data", [])
    if not user_rows:
        return []
    ids = [str(row.get("id", "")) for row in user_rows if row.get("id")]
    streams_url = TWITCH_STREAMS_URL + "?" + urllib.parse.urlencode([("user_id", uid) for uid in ids])
    stream_rows = _http_json(streams_url, headers=headers).get("data", [])
    streams = {str(row.get("user_id")): row for row in stream_rows}
    result = []
    for user in user_rows:
        uid = str(user.get("id", ""))
        stream = streams.get(uid)
        result.append({
            "id": uid,
            "login": str(user.get("login", "") or "").lower(),
            "name": str(user.get("display_name", "") or user.get("login", "")),
            "description": str(user.get("description", "") or ""),
            "profile_image": str(user.get("profile_image_url", "") or ""),
            "url": f"https://www.twitch.tv/{urllib.parse.quote(str(user.get('login', '')))}",
            "live": bool(stream),
            "title": str((stream or {}).get("title", "") or ""),
            "game": str((stream or {}).get("game_name", "") or ""),
            "viewers": int((stream or {}).get("viewer_count") or 0),
            "started_at": str((stream or {}).get("started_at", "") or ""),
            "language": str((stream or {}).get("language", "") or ""),
            "thumbnail": str((stream or {}).get("thumbnail_url", "") or ""),
        })
    indexed = {row["login"]: row for row in result}
    return [indexed[name] for name in logins if name in indexed]


@st.cache_data(ttl=45, show_spinner=False)
def fetch_public_live_status(tid):
    """Public Twitch live state for a published StreamDex creator profile."""
    try:
        tid = str(tid or "")
        if not re.fullmatch(r"[0-9]{1,15}", tid):
            return {"available": False, "live": False}
        client_id, client_secret = _credentials()
        token = _app_token(client_id, client_secret)
        url = TWITCH_STREAMS_URL + "?" + urllib.parse.urlencode({"user_id": tid})
        result = _http_json(url, headers={"Client-Id": client_id, "Authorization": f"Bearer {token}"})
        rows = result.get("data", [])
        if not isinstance(rows, list) or not rows:
            return {"available": True, "live": False}
        stream = rows[0]
        if not isinstance(stream, dict):
            return {"available": True, "live": False}
        return {
            "available": True,
            "live": True,
            "title": str(stream.get("title") or ""),
            "game": str(stream.get("game_name") or ""),
            "viewers": int(stream.get("viewer_count") or 0),
            "started_at": str(stream.get("started_at") or ""),
            "thumbnail": str(stream.get("thumbnail_url") or "").replace("{width}", "640").replace("{height}", "360"),
            "language": str(stream.get("language") or ""),
        }
    except Exception:
        return {"available": False, "live": False}


def _fmt_started(value):
    try:
        from datetime import datetime
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone().strftime("%H:%M")
    except Exception:
        return "—"



def _creator_access_token(tid):
    """Liefert nur das Zugriffstoken der passend angemeldeten Twitch-Identität."""
    session_tid = str(st.session_state.get("twitch_oauth_tid", "") or "")
    if session_tid != str(tid):
        return None
    token = str(st.session_state.get("twitch_oauth_access_token", "") or "")
    try:
        expires_at = float(st.session_state.get("twitch_oauth_expires_at", 0) or 0)
    except (TypeError, ValueError):
        expires_at = 0
    if token and time.time() < expires_at - 60:
        return token

    refresh_token = str(st.session_state.get("twitch_oauth_refresh_token", "") or "")
    if not refresh_token:
        return None
    try:
        client_id, client_secret = _credentials()
        result = _http_json(
            TWITCH_TOKEN_URL,
            method="POST",
            form={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        refreshed = str(result.get("access_token", "") or "")
        if not refreshed:
            return None
        checked = _http_json(
            TWITCH_VALIDATE_URL,
            headers={"Authorization": f"OAuth {refreshed}"},
        )
        if str(checked.get("user_id", "") or "") != str(tid):
            return None
        try:
            expires_in = max(60, int(result.get("expires_in") or 14400))
        except (TypeError, ValueError):
            expires_in = 14400
        st.session_state["twitch_oauth_access_token"] = refreshed
        st.session_state["twitch_oauth_refresh_token"] = str(result.get("refresh_token") or refresh_token)
        st.session_state["twitch_oauth_expires_at"] = time.time() + expires_in
        new_scopes = result.get("scope")
        if isinstance(new_scopes, list):
            st.session_state["twitch_oauth_scopes"] = new_scopes
        return refreshed
    except Exception:
        # Tokens und OAuth-Fehlerdetails niemals in die Oberfläche oder Logs übernehmen.
        return None


def _helix_get(path, token, params=None):
    client_id, _ = _credentials()
    query = urllib.parse.urlencode(params or {})
    url = f"{TWITCH_API_BASE}/{path.lstrip('/')}" + (f"?{query}" if query else "")
    return _http_json(
        url,
        headers={"Client-Id": client_id, "Authorization": f"Bearer {token}"},
    )


def _creator_metrics(tid, token, force=False):
    """Lädt die verfügbaren eigenen Kanalmetriken und hält sie kurz sitzungsintern vor."""
    cache = st.session_state.get("sd_radar_creator_metrics_cache")
    now = time.time()
    if not force and isinstance(cache, dict) and cache.get("tid") == str(tid) and now - float(cache.get("ts", 0)) < 45:
        cached = cache.get("data")
        if isinstance(cached, dict):
            return cached

    now_utc = datetime.now(timezone.utc)
    month_ago = (now_utc - timedelta(days=30)).isoformat(timespec="seconds").replace("+00:00", "Z")
    requests = {
        "user": ("users", {"id": str(tid)}),
        "channel": ("channels", {"broadcaster_id": str(tid)}),
        "stream": ("streams", {"user_id": str(tid)}),
        "followers": ("channels/followers", {"broadcaster_id": str(tid), "first": 1}),
        "subscriptions": ("subscriptions", {"broadcaster_id": str(tid), "first": 1}),
        "bits": ("bits/leaderboard", {"count": 10, "period": "month", "started_at": month_ago}),
        "goals": ("goals", {"broadcaster_id": str(tid)}),
        "hypetrain": ("hypetrain/status", {"broadcaster_id": str(tid)}),
        "ads": ("channels/ads", {"broadcaster_id": str(tid)}),
        "polls": ("polls", {"broadcaster_id": str(tid), "first": 20}),
        "predictions": ("predictions", {"broadcaster_id": str(tid), "first": 20}),
        "charity": ("charity/campaigns", {"broadcaster_id": str(tid)}),
        "videos": ("videos", {"user_id": str(tid), "type": "archive", "first": 10, "sort": "time"}),
        "clips": ("clips", {"broadcaster_id": str(tid), "first": 10, "started_at": (now_utc - timedelta(days=7)).isoformat(timespec="seconds").replace("+00:00", "Z"), "ended_at": now_utc.isoformat(timespec="seconds").replace("+00:00", "Z")}),
    }
    result = {}
    for key, (path, params) in requests.items():
        try:
            result[key] = _helix_get(path, token, params)
        except Exception:
            result[key] = {"data": [], "_unavailable": True}
    st.session_state["sd_radar_creator_metrics_cache"] = {"tid": str(tid), "ts": now, "data": result}
    return result


def _api_rows(metrics, key):
    item = metrics.get(key, {})
    if not isinstance(item, dict):
        return []
    rows = item.get("data", [])
    return rows if isinstance(rows, list) else []


def _api_total(metrics, key):
    item = metrics.get(key, {})
    if not isinstance(item, dict) or item.get("_unavailable") or "total" not in item:
        return None
    try:
        return int(item.get("total") or 0)
    except (TypeError, ValueError):
        return None


def _record_stream_sample(tid, stream):
    """Sammelt höchstens alle fünf Minuten eine eigene Zuschauer-Messung in Firebase."""
    try:
        root = db.reference(f"radar_analytics/{tid}")
        active_id = str(root.child("active_stream_id").get() or "")
        now = int(time.time())
        if stream:
            stream_id = str(stream.get("id") or "")
            if not stream_id:
                return
            session_ref = root.child("sessions").child(stream_id)
            saved = session_ref.get() or {}
            try:
                twitch_started = datetime.fromisoformat(str(stream.get("started_at", "")).replace("Z", "+00:00")).timestamp()
            except (TypeError, ValueError, OverflowError):
                twitch_started = now
            session_ref.update({
                "stream_id": stream_id,
                "started_at_unix": int(saved.get("started_at_unix") or twitch_started),
                "title": str(stream.get("title") or "")[:300],
                "game": str(stream.get("game_name") or "")[:120],
                "last_observed_at": now,
            })
            try:
                last_sample = int(saved.get("last_sample_at") or 0)
            except (TypeError, ValueError):
                last_sample = 0
            if now - last_sample >= 300:
                session_ref.child("samples").child(str(now)).set({
                    "ts": now,
                    "viewers": int(stream.get("viewer_count") or 0),
                })
                session_ref.child("last_sample_at").set(now)
            if active_id and active_id != stream_id:
                root.child("sessions").child(active_id).update({"ended_at_unix": now})
            root.child("active_stream_id").set(stream_id)
        elif active_id:
            root.child("sessions").child(active_id).update({"ended_at_unix": now})
            root.child("active_stream_id").set("")
    except Exception:
        # Statistik-Messung darf das eigentliche Dashboard nicht blockieren.
        return


def _tracked_sessions(tid):
    try:
        raw = db.reference(f"radar_analytics/{tid}/sessions").get() or {}
    except Exception:
        return []
    if not isinstance(raw, dict):
        return []
    sessions = []
    for stream_id, session in raw.items():
        if not isinstance(session, dict):
            continue
        samples_raw = session.get("samples", {})
        samples = []
        if isinstance(samples_raw, dict):
            for sample in samples_raw.values():
                if isinstance(sample, dict):
                    try:
                        samples.append({"ts": int(sample.get("ts") or 0), "viewers": int(sample.get("viewers") or 0)})
                    except (TypeError, ValueError):
                        pass
        samples.sort(key=lambda row: row["ts"])
        sessions.append({
            "stream_id": str(stream_id),
            "started_at_unix": int(session.get("started_at_unix") or 0),
            "ended_at_unix": int(session.get("ended_at_unix") or 0),
            "title": str(session.get("title") or ""),
            "game": str(session.get("game") or ""),
            "samples": samples,
        })
    return sorted(sessions, key=lambda row: row["started_at_unix"], reverse=True)


def _record_daily_snapshot(tid, followers, subscribers, live):
    """Speichert pro UTC-Tag einen Vergleichspunkt, damit Trends erst ab jetzt entstehen."""
    try:
        root = db.reference(f"radar_analytics/{tid}/daily_snapshots")
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        day_ref = root.child(day)
        if not day_ref.get():
            snapshot = {"date": day, "ts": int(time.time())}
            if followers is not None:
                snapshot["followers"] = int(followers)
            if subscribers is not None:
                snapshot["subscribers"] = int(subscribers)
            if live:
                snapshot["viewer_count"] = int(live.get("viewer_count") or 0)
            day_ref.set(snapshot)
        raw = root.get() or {}
        if not isinstance(raw, dict):
            return []
        # Begrenze die gespeicherte Verlaufshistorie auf ein Jahr.
        dates = sorted(str(key) for key in raw if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(key)))
        for old_day in dates[:-365]:
            root.child(old_day).delete()
        rows = [value for key, value in raw.items() if key in dates and isinstance(value, dict)]
        rows.sort(key=lambda row: str(row.get("date") or ""))
        return rows
    except Exception:
        return []


@st.fragment(run_every=300)
def _render_creator_analytics(tid, username, reauth_url=None):
    """Eigene Twitch-Kennzahlen plus transparent markierte StreamDex-Messwerte."""
    st.markdown("### 📈 Deine Twitch-Creator-Statistiken")
    st.caption("Privater Bereich für dein eigenes, angemeldetes Twitch-Konto.")
    token = _creator_access_token(tid)
    if not token:
        st.warning(
            "Für deine persönlichen Twitch-Statistiken ist eine erneute Twitch-Freigabe nötig. "
            "Damit kann StreamDex nur die ausdrücklich angefragten Statistikbereiche lesen."
        )
        if reauth_url:
            st.link_button("🟣 Twitch-Statistiken verbinden", reauth_url, type="primary")
        st.caption("Das Twitch-Zugriffstoken wird nur in der laufenden Sitzung gehalten, nicht in Firebase gespeichert.")
        return

    refresh_col, status_col = st.columns([1, 2], vertical_alignment="center")
    if refresh_col.button("🔄 Statistiken aktualisieren", key="sd_radar_analytics_refresh"):
        st.session_state.pop("sd_radar_creator_metrics_cache", None)
        st.rerun()
    status_col.caption("Live-Daten werden automatisch etwa alle 5 Minuten neu abgefragt.")

    try:
        metrics = _creator_metrics(tid, token)
    except Exception:
        st.error("Die Twitch-Statistiken konnten gerade nicht geladen werden. Bitte später erneut versuchen.")
        return

    user_rows = _api_rows(metrics, "user")
    channel_rows = _api_rows(metrics, "channel")
    live_rows = _api_rows(metrics, "stream")
    videos = _api_rows(metrics, "videos")
    clips = _api_rows(metrics, "clips")
    live = live_rows[0] if live_rows else None
    channel = channel_rows[0] if channel_rows else {}
    user = user_rows[0] if user_rows else {}
    _record_stream_sample(tid, live)

    tracked = _tracked_sessions(tid)
    current_session = next((s for s in tracked if live and s["stream_id"] == str(live.get("id"))), None)
    sample_session = current_session or (tracked[0] if tracked else None)
    samples = sample_session.get("samples", []) if sample_session else []
    sampled_values = [int(row["viewers"]) for row in samples]
    sampled_avg = round(sum(sampled_values) / len(sampled_values)) if sampled_values else None
    sampled_max = max(sampled_values) if sampled_values else None
    latest_ten_video_views = sum(int(v.get("view_count") or 0) for v in videos[:10])
    bits_rows = _api_rows(metrics, "bits")
    top_bits = max((int(row.get("score") or 0) for row in bits_rows), default=None)
    recent_followers = _api_total(metrics, "followers")
    subscribers = _api_total(metrics, "subscriptions")
    snapshot_history = _record_daily_snapshot(tid, recent_followers, subscribers, live)
    today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    prior_snapshots = [row for row in snapshot_history if str(row.get("date") or "") < today_utc]
    previous_snapshot = prior_snapshots[-1] if prior_snapshots else {}
    follower_delta = (
        recent_followers - int(previous_snapshot["followers"])
        if recent_followers is not None and previous_snapshot.get("followers") is not None else None
    )
    subscriber_delta = (
        subscribers - int(previous_snapshot["subscribers"])
        if subscribers is not None and previous_snapshot.get("subscribers") is not None else None
    )

    display_name = str(user.get("display_name") or user.get("login") or username)
    st.markdown(
        f'<div class="sd-radar-card" style="min-height:0;margin:0 0 14px">'
        f'<div class="sd-radar-card-head">'
        f'<div><div class="sd-radar-name">{html.escape(display_name)}</div>'
        f'<div class="sd-radar-login">@{html.escape(str(user.get("login") or username))}</div></div>'
        f'<span class="sd-radar-live {"on" if live else "off"}"><i></i>{"LIVE" if live else "OFFLINE"}</span>'
        f'</div>'
        f'<div class="sd-radar-stream-title">{html.escape(str((live or {}).get("title") or channel.get("title") or "Aktuell kein laufender Stream"))}</div>'
        f'<div class="sd-radar-meta"><span>🎮 {html.escape(str((live or {}).get("game_name") or channel.get("game_name") or "Keine Kategorie"))}</span>'
        f'<span>🌐 {html.escape(str(channel.get("broadcaster_language") or "Sprache nicht angegeben").upper())}</span>'
        f'<span>🗓️ Twitch-Konto seit {html.escape(str(user.get("created_at", "") or "unbekannt")[:10])}</span></div></div>',
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🔴 Aktuelle Zuschauer", f'{int(live.get("viewer_count") or 0):,}'.replace(",", ".") if live else "Offline")
    c2.metric("👥 Follower gesamt", f"{recent_followers:,}".replace(",", ".") if recent_followers is not None else "—")
    c3.metric("⭐ Abonnenten", f"{subscribers:,}".replace(",", ".") if subscribers is not None else "Nicht verfügbar")
    c4.metric("🎬 Views (letzte 10 VODs)", f"{latest_ten_video_views:,}".replace(",", ".") if videos else "—")

    s1, s2, s3, s4 = st.columns(4)
    s1.metric("📊 Ø Zuschauer (gemessen)", f"{sampled_avg:,}".replace(",", ".") if sampled_avg is not None else "Noch keine Messung")
    s2.metric("🚀 Peak-Zuschauer (gemessen)", f"{sampled_max:,}".replace(",", ".") if sampled_max is not None else "Noch keine Messung")
    s3.metric("💎 Höchster Bits-Score", f"{top_bits:,}".replace(",", ".") if top_bits is not None else "—")
    s4.metric("📼 Verfügbare VODs", len(videos))

    d1, d2 = st.columns(2)
    d1.metric("➕ Follower seit Tagesvergleich", f"{follower_delta:+,}".replace(",", ".") if follower_delta is not None else "Wird aufgebaut")
    d2.metric("➕ Abos seit Tagesvergleich", f"{subscriber_delta:+,}".replace(",", ".") if subscriber_delta is not None else "Wird aufgebaut")
    if previous_snapshot:
        st.caption(f"Vergleich mit der letzten älteren Tagesmessung: {previous_snapshot.get('date', '—')} UTC. Die Verlaufshistorie beginnt ab der Nutzung von StreamDex.")

    st.caption(
        "Ø- und Peak-Zuschauer sind eigene StreamDex-Messungen und keine rückwirkend importierten Twitch-Analytics. "
        "Die Messung läuft ungefähr alle fünf Minuten, solange dein Dashboard geöffnet ist."
    )
    if live:
        try:
            started = datetime.fromisoformat(str(live.get("started_at", "")).replace("Z", "+00:00"))
            elapsed = max(0, int((datetime.now(timezone.utc) - started).total_seconds()))
            st.info(f"🔴 Dein Stream läuft seit etwa {elapsed // 3600} Std. {(elapsed % 3600) // 60} Min.")
        except (TypeError, ValueError):
            st.info("🔴 Du bist gerade live auf Twitch.")

    if samples:
        with st.expander("📈 Zuschauerverlauf aus StreamDex-Messungen", expanded=bool(live)):
            st.line_chart({"Zuschauer": sampled_values}, height=220)
            st.caption(f"{len(samples)} Messpunkte in dieser Session · Maximum {sampled_max:,} · Durchschnitt {sampled_avg:,}")

    goals = _api_rows(metrics, "goals")
    with st.expander("🎯 Creator-Ziele", expanded=bool(goals)):
        if not goals:
            st.caption("Aktuell kein Twitch-Creator-Ziel verfügbar oder die Berechtigung fehlt.")
        for goal in goals:
            try:
                current = int(goal.get("current_amount") or 0)
                target = int(goal.get("target_amount") or 0)
            except (TypeError, ValueError):
                current, target = 0, 0
            label = str(goal.get("description") or goal.get("type") or "Creator-Ziel")
            st.markdown(f"**{html.escape(label)}** · {current:,} / {target:,}".replace(",", "."))
            st.progress(min(1.0, current / target) if target > 0 else 0.0)

    trains = _api_rows(metrics, "hypetrain")
    with st.expander("🚂 Hype Train", expanded=False):
        train_data = trains[0] if trains else {}
        current_train = train_data.get("current") if isinstance(train_data, dict) else None
        record_train = train_data.get("all_time_high") if isinstance(train_data, dict) else None
        if isinstance(current_train, dict):
            a, b, c = st.columns(3)
            a.metric("Aktuelles Level", current_train.get("level", "—"))
            b.metric("Fortschritt", f'{int(current_train.get("progress") or 0):,} / {int(current_train.get("goal") or 0):,}'.replace(",", "."))
            c.metric("Punkte gesamt", f'{int(current_train.get("total") or 0):,}'.replace(",", "."))
            goal = int(current_train.get("goal") or 0)
            progress = int(current_train.get("progress") or 0)
            st.progress(min(1.0, progress / goal) if goal > 0 else 0.0)
        else:
            st.caption("Aktuell kein Hype Train aktiv.")
        if isinstance(record_train, dict):
            st.caption(f"Rekord: Level {record_train.get('level', '—')} · {int(record_train.get('total') or 0):,} Punkte".replace(",", "."))

    with st.expander("💎 Bits-Leaderboard · letzte 30 Tage", expanded=bool(bits_rows)):
        if bits_rows:
            st.dataframe(
                [{"Rang": i + 1, "Name": row.get("user_name") or row.get("user_login") or "Twitch-Nutzer",
                  "Bits": int(row.get("score") or 0)} for i, row in enumerate(bits_rows)],
                use_container_width=True, hide_index=True,
            )
        else:
            st.caption("Twitch hat für diesen Zeitraum keine Bits-Daten zurückgegeben oder die Berechtigung fehlt.")

    with st.expander("🎬 Letzte Streams / VODs", expanded=bool(videos)):
        if videos:
            st.dataframe(
                [{"Titel": str(v.get("title") or "Ohne Titel"), "Aufrufe": int(v.get("view_count") or 0),
                  "Dauer": str(v.get("duration") or "—"), "Erstellt": str(v.get("created_at") or "")[:16].replace("T", " "),
                  "VOD": str(v.get("url") or "")} for v in videos],
                use_container_width=True, hide_index=True,
                column_config={"VOD": st.column_config.LinkColumn("VOD öffnen", display_text="Ansehen")},
            )
        else:
            st.caption("Keine archivierten Streams verfügbar. Prüfe, ob Twitch VODs für deinen Kanal speichert.")

    with st.expander("✂️ Deine Clips · letzte 7 Tage", expanded=False):
        if clips:
            st.dataframe(
                [{"Titel": str(c.get("title") or "Clip"), "Aufrufe": int(c.get("view_count") or 0),
                  "Erstellt": str(c.get("created_at") or "")[:16].replace("T", " "),
                  "Clip": str(c.get("url") or "")} for c in clips],
                use_container_width=True, hide_index=True,
                column_config={"Clip": st.column_config.LinkColumn("Clip öffnen", display_text="Ansehen")},
            )
        else:
            st.caption("Twitch hat keine Clips aus den letzten 30 Tagen zurückgegeben.")

    with st.expander("📈 Verlauf deiner Follower & Abos", expanded=False):
        valid_follower_snapshots = [row for row in snapshot_history if row.get("followers") is not None]
        if len(valid_follower_snapshots) >= 2:
            valid_follower_snapshots = valid_follower_snapshots[-30:]
            st.line_chart({"Follower": [int(row["followers"]) for row in valid_follower_snapshots]}, height=200)
            st.dataframe(
                [{"Tag (UTC)": row.get("date", "—"),
                  "Follower": int(row["followers"]) if row.get("followers") is not None else "—",
                  "Abos": int(row["subscribers"]) if row.get("subscribers") is not None else "—"}
                 for row in reversed(valid_follower_snapshots)],
                use_container_width=True, hide_index=True,
            )
        else:
            st.caption("Die Verlaufskurve entsteht automatisch aus täglichen Messpunkten. Nach ein paar Tagen werden die ersten Veränderungen sichtbar.")

    charity = _api_rows(metrics, "charity")
    if charity:
        campaign = charity[0]
        with st.expander("💜 Aktuelle Charity-Kampagne", expanded=False):
            st.markdown(f"**{html.escape(str(campaign.get('charity_name') or 'Charity'))}**")
            st.write(str(campaign.get("charity_description") or ""))
            st.metric("Spenden gesammelt", f'{int(campaign.get("current_amount", {}).get("value") or 0):,}'.replace(",", "."))
            st.caption(f"Ziel: {campaign.get('target_amount', {}).get('value', '—')} · Währung: {campaign.get('current_amount', {}).get('currency', '—')}")

    polls = _api_rows(metrics, "polls")
    predictions = _api_rows(metrics, "predictions")
    with st.expander("📊 Umfragen & Vorhersagen", expanded=False):
        if polls:
            st.markdown("**Letzte Umfragen**")
            st.dataframe(
                [{"Umfrage": str(p.get("title") or "Umfrage"),
                  "Status": str(p.get("status") or "—"),
                  "Stimmen": sum(int(x.get("total_votes") or 0) for x in (p.get("choices") or []))}
                 for p in polls[:10]],
                use_container_width=True, hide_index=True,
            )
        if predictions:
            st.markdown("**Letzte Vorhersagen**")
            st.dataframe(
                [{"Vorhersage": str(p.get("title") or "Vorhersage"), "Status": str(p.get("status") or "—"),
                  "Punkte": sum(int(x.get("channel_points") or 0) for x in (p.get("outcomes") or []))}
                 for p in predictions[:10]],
                use_container_width=True, hide_index=True,
            )
        if not polls and not predictions:
            st.caption("Keine Umfragen oder Vorhersagen verfügbar; eventuell gibt es noch keine oder die Freigabe fehlt.")

    ads = _api_rows(metrics, "ads")
    if ads:
        ad = ads[0]
        with st.expander("📺 Werbeplan", expanded=False):
            next_ad = str(ad.get("next_ad_at") or "")
            last_ad = str(ad.get("last_ad_at") or "")
            a, b, c = st.columns(3)
            a.metric("Nächste Werbung", next_ad[:16].replace("T", " ") or "Nicht geplant")
            b.metric("Letzte Werbung", last_ad[:16].replace("T", " ") or "—")
            c.metric("Werbefrei", f'{int(ad.get("preroll_free_time") or 0)} Sek.')

    recent_sessions = [s for s in tracked if s.get("samples")]
    if recent_sessions:
        with st.expander("🗂️ Frühere StreamDex-Messungen", expanded=False):
            session_rows = []
            for session in recent_sessions[:10]:
                values = [int(s["viewers"]) for s in session["samples"]]
                session_rows.append({
                    "Stream gestartet": datetime.fromtimestamp(session["started_at_unix"]).strftime("%d.%m.%Y %H:%M") if session["started_at_unix"] else "—",
                    "Titel": session["title"] or "Ohne Titel",
                    "Messpunkte": len(values),
                    "Ø Zuschauer": round(sum(values) / len(values)),
                    "Peak": max(values),
                })
            st.dataframe(session_rows, use_container_width=True, hide_index=True)


def render_radar(tid, username, reauth_url=None):
    """Rendert den authentifizierten, kontobezogenen StreamDex Radar."""
    st.markdown(
        """
        <div class="sd-radar-hero">
          <div class="sd-radar-kicker">STREAMDEX OS / CREATOR ANALYTICS</div>
          <h1>Dein <span>Streamer-Dashboard.</span></h1>
          <p>Deine eigenen Twitch-Zahlen: Live-Zuschauer, Follower, Abonnenten, Bits, VOD-Aufrufe, Ziele und dein von StreamDex erfasster Zuschauerverlauf.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <style>
        .sd-radar-hero{border:1px solid rgba(139,92,246,.32);border-radius:18px;padding:24px 26px;margin:0 0 18px;
          background:radial-gradient(ellipse at 85% 20%,rgba(34,211,238,.12),transparent 40%),
          linear-gradient(115deg,rgba(15,23,42,.98),rgba(35,25,71,.94) 58%,rgba(8,47,73,.88));
          box-shadow:0 18px 45px rgba(0,0,0,.22)}
        .sd-radar-kicker{font:700 .68rem 'JetBrains Mono',monospace;letter-spacing:.14em;color:#c4b5fd}
        .sd-radar-hero h1{font-size:clamp(1.8rem,3vw,2.6rem);font-weight:800;letter-spacing:-.05em;margin:12px 0 9px;color:#f8fafc}
        .sd-radar-hero h1 span{background:linear-gradient(90deg,#c084fc,#818cf8,#67e8f9);-webkit-background-clip:text;color:transparent}
        .sd-radar-hero p{font-size:.9rem;line-height:1.7;color:#cbd5e1;max-width:780px;margin:0}
        .sd-radar-card{height:100%;min-height:168px;border:1px solid rgba(148,163,184,.16);border-radius:15px;padding:16px;
          background:linear-gradient(145deg,rgba(15,23,42,.92),rgba(11,17,34,.94));box-shadow:0 8px 24px rgba(0,0,0,.15)}
        .sd-radar-card-head{display:flex;align-items:center;gap:11px;margin-bottom:12px}
        .sd-radar-avatar{width:46px;height:46px;object-fit:cover;border-radius:13px;border:1px solid rgba(167,139,250,.45);background:#1e1b4b}
        .sd-radar-avatar-empty{display:grid;place-items:center;width:46px;height:46px;border-radius:13px;background:#29204b;color:#c4b5fd;font-size:1.2rem}
        .sd-radar-name{font-weight:800;font-size:.97rem;color:#f1f5ff}
        .sd-radar-login{font-size:.72rem;color:#94a3b8;margin-top:3px}
        .sd-radar-live{display:inline-flex;gap:6px;align-items:center;font-size:.67rem;font-weight:800;letter-spacing:.04em;padding:5px 8px;border-radius:99px}
        .sd-radar-live.on{color:#86efac;background:rgba(34,197,94,.1);border:1px solid rgba(34,197,94,.26)}
        .sd-radar-live.off{color:#aab6d0;background:rgba(148,163,184,.08);border:1px solid rgba(148,163,184,.17)}
        .sd-radar-live i{display:inline-block;width:6px;height:6px;border-radius:50%;background:currentColor}
        .sd-radar-stream-title{font-size:.82rem;font-weight:700;color:#e2e8f0;line-height:1.5;margin:11px 0 7px}
        .sd-radar-meta{display:flex;gap:7px;flex-wrap:wrap;color:#9caed0;font-size:.7rem}
        .sd-radar-meta span{padding:5px 8px;border:1px solid rgba(148,163,184,.13);border-radius:7px;background:rgba(15,23,42,.6)}
        .sd-radar-thumb{width:100%;border-radius:9px;border:1px solid rgba(148,163,184,.14);margin:5px 0 8px}
        @media(max-width:700px){.sd-radar-hero{padding:18px}.sd-radar-card{min-height:0}}
        </style>
        """,
        unsafe_allow_html=True,
    )

    _render_creator_analytics(tid, username, reauth_url)
