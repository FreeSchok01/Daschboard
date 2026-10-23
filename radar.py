"""StreamDex Radar: persönliche Twitch-Watchlist mit Live-Status und StreamDex-Statistiken."""
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

import streamlit as st
from firebase_admin import db

TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
TWITCH_USERS_URL = "https://api.twitch.tv/helix/users"
TWITCH_STREAMS_URL = "https://api.twitch.tv/helix/streams"
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


def _fmt_started(value):
    try:
        from datetime import datetime
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone().strftime("%H:%M")
    except Exception:
        return "—"


def render_radar(tid, username):
    """Rendert den authentifizierten, kontobezogenen StreamDex Radar."""
    st.markdown(
        """
        <div class="sd-radar-hero">
          <div class="sd-radar-kicker">STREAMDEX OS / CREATOR RADAR</div>
          <h1>Dein <span>Streamer-Radar.</span></h1>
          <p>Live-Status, aktuelle Streams und Community-Statistiken deiner Lieblingskanäle – in einer persönlichen Übersicht.</p>
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

    try:
        watchlist = _load_watchlist(str(tid))
    except Exception:
        st.error("Deine Radar-Watchlist konnte nicht geladen werden. Bitte versuche es erneut.")
        return

    with st.container(border=True):
        st.markdown("#### ➕ Streamer zur Watchlist hinzufügen")
        c1, c2 = st.columns([4, 1], vertical_alignment="bottom")
        with c1:
            value = st.text_input(
                "Twitch-Name oder Kanal-Link",
                placeholder="z. B. shroud oder twitch.tv/shroud",
                key="sd_radar_add_name",
                label_visibility="collapsed",
            )
        with c2:
            add = st.button("＋ Hinzufügen", type="primary", use_container_width=True, key="sd_radar_add")
        st.caption(f"Deine Liste ist privat für dein StreamDex-Konto. Maximal {MAX_WATCHLIST} Kanäle.")
        if add:
            normalized = _normalize_login(value)
            if not normalized:
                st.warning("Bitte einen gültigen Twitch-Namen oder Twitch-Kanal-Link eingeben.")
            elif normalized in watchlist:
                st.info("Dieser Kanal ist bereits in deiner Watchlist.")
            elif len(watchlist) >= MAX_WATCHLIST:
                st.warning(f"Du kannst maximal {MAX_WATCHLIST} Kanäle beobachten.")
            else:
                try:
                    _save_watchlist(str(tid), watchlist + [normalized])
                    _fetch_channels.clear()
                    st.session_state.pop("sd_radar_add_name", None)
                    st.success(f"@{normalized} wurde zu deinem Radar hinzugefügt.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Speichern nicht möglich: {exc}")

    c_refresh, c_live, c_all = st.columns([1, 1, 2])
    if c_refresh.button("🔄 Live-Daten aktualisieren", use_container_width=True, key="sd_radar_refresh"):
        _fetch_channels.clear()
        st.rerun()

    try:
        with st.spinner("Twitch-Live-Status wird geladen …"):
            channels = _fetch_channels(tuple(watchlist))
    except Exception as exc:
        channels = []
        st.error(str(exc))

    live_channels = [c for c in channels if c["live"]]
    offline_channels = [c for c in channels if not c["live"]]
    total_viewers = sum(c["viewers"] for c in live_channels)
    category_counts = {}
    for channel in live_channels:
        if channel["game"]:
            category_counts[channel["game"]] = category_counts.get(channel["game"], 0) + 1
    top_category = max(category_counts, key=category_counts.get) if category_counts else "—"
    c_live.metric("🔴 Gerade live", len(live_channels))
    c_all.metric("👥 In deiner Liste", len(watchlist))
    c_refresh.metric("👁 Zuschauer gesamt", f"{total_viewers:,}".replace(",", "."))
    col_category = st.columns(1)[0]
    col_category.metric("🎮 Häufigste Kategorie", top_category)
    st.caption(f"Zuletzt geprüft: {time.strftime('%H:%M:%S')} · {len(offline_channels)} offline")

    q_col, f_col = st.columns([3, 1])
    query = q_col.text_input("🔎 Watchlist durchsuchen", placeholder="Kanalname, Spiel oder Streamtitel …", key="sd_radar_search")
    mode = f_col.selectbox("Status", ["Alle", "Nur live", "Offline"], key="sd_radar_filter")
    shown = [
        c for c in channels
        if (not query or query.lower() in (c["name"] + " " + c["login"] + " " + c["title"] + " " + c["game"]).lower())
        and (mode == "Alle" or (mode == "Nur live" and c["live"]) or (mode == "Offline" and not c["live"]))
    ]

    if not watchlist:
        st.info("Deine Watchlist ist noch leer. Füge oben einen oder mehrere Twitch-Kanäle hinzu, um Live-Status und Streams zu beobachten.")
        return
    missing = set(watchlist) - {c["login"] for c in channels}
    if missing:
        st.warning("Diese Kanäle wurden bei Twitch nicht gefunden oder konnten nicht geladen werden: " + ", ".join("@" + n for n in sorted(missing)))
    if not channels:
        st.info("Noch keine Kanaldaten verfügbar. Prüfe deine Twitch-API-Zugangsdaten und aktualisiere die Seite.")
        return
    if not shown:
        st.info("Für diese Suche oder diesen Statusfilter wurden keine Kanäle gefunden.")
        return

    st.markdown("### 📡 Deine Kanäle")
    for offset in range(0, len(shown), 3):
        cols = st.columns(3)
        for col, channel in zip(cols, shown[offset:offset + 3]):
            with col:
                with st.container(border=True):
                    image = channel.get("profile_image")
                    if image:
                        st.image(image, width=58)
                    status = "🔴 LIVE" if channel["live"] else "⚪ OFFLINE"
                    st.markdown(
                        f'<span class="sd-radar-live {"on" if channel["live"] else "off"}"><i></i>{status}</span>',
                        unsafe_allow_html=True,
                    )
                    st.markdown(f"### {html.escape(channel['name'])}")
                    st.caption("@" + html.escape(channel["login"]))
                    if channel["live"]:
                        title = html.escape(channel["title"] or "Live – ohne Titel")
                        game = html.escape(channel["game"] or "Kategorie unbekannt")
                        st.markdown(f'<div class="sd-radar-stream-title">{title}</div>', unsafe_allow_html=True)
                        meta = f'<div class="sd-radar-meta"><span>👁 {channel["viewers"]:,} Zuschauer</span><span>🎮 {game}</span><span>⏱ seit {html.escape(_fmt_started(channel["started_at"]))}</span></div>'
                        st.markdown(meta, unsafe_allow_html=True)
                        thumb = channel.get("thumbnail", "").replace("{width}", "640").replace("{height}", "360")
                        if thumb.startswith("https://static-cdn.jtvnw.net/"):
                            st.image(thumb, use_container_width=True)
                        st.link_button("▶ Stream öffnen", channel["url"], use_container_width=True)
                    else:
                        st.caption("Aktuell kein laufender Twitch-Stream.")
                        st.link_button("Twitch-Kanal öffnen", channel["url"], use_container_width=True)

                    if st.button("Entfernen", key=f"sd_radar_remove_{tid}_{channel['login']}", use_container_width=True):
                        try:
                            _save_watchlist(str(tid), [n for n in watchlist if n != channel["login"]])
                            _fetch_channels.clear()
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Entfernen fehlgeschlagen: {exc}")

    st.caption(
        "Live-Status, Streamtitel, Kategorie und Zuschauerzahlen kommen direkt von Twitch. "
        "Die Gesamtzahlen beziehen sich auf die Kanäle deiner privaten Watchlist; sie sind keine offiziellen Kanal-Analytics. "
        "Die Daten werden beim Aktualisieren neu abgerufen und sind kein sekundengenauer Liveticker."
    )
