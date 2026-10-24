"""Streamer-Dashboard mit geschütztem Zugriff über Einmal-Tokens."""
import hashlib
import hmac
import html
import json
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from streamlit_cookies_controller import CookieController
from firebase_admin import db

from beta_apply import _apply_form, render_logged_in_beta_status
from downloads import (beta_link, lurk_repo, render_member_downloads, render_public_downloads,
                       settings as download_settings, update_notice)
from shop import owned_games, CSS
from events import render_event_manager
from planner import render_planner
from radar import render_radar
from feedback_hub import render_feedback_hub
from streamdex_suite import render_streamdex_suite
from creator_profile import render_creator_profile
from legacy import render_legacy
from clips_manager import render_clips_manager
from community_events import render_community_integrations
from theme import render_empty_state, render_os_navigation
from onboarding import render_first_steps, render_guided_tour
from privacy_security import (
    collect_user_shared_data,
    is_valid_twitch_id,
    make_signed_oauth_state,
    oauth_state_key,
    oauth_state_record_is_active,
    plan_shared_account_deletions,
    safe_exception_label,
    verify_signed_oauth_state,
)

TZ = ZoneInfo("Europe/Berlin")
SERVER_TS = {".sv": "timestamp"}

STAT_KEYS = {
    "giveaways": "Giveaways gesamt",
    "giveaway_participants": "Teilnahmen",
    "giveaways_7d": "Giveaways (7 Tage)",
    "giveaways_30d": "Giveaways (30 Tage)",
    "viewers": "Viewer erfasst",
    "checkins": "Check-ins",
    "slot_spins": "Slot-Spins",
    "megaslot_spins": "Mega-Slot-Spins",
    "fish_catches": "Fänge (Angeln)",
    "harvests": "Ernten (Farm)",
    "raids": "Raids empfangen",
}


def _fmt_ts(ms):
    try:
        return datetime.fromtimestamp(int(ms) / 1000, TZ).strftime("%d.%m.%Y %H:%M")
    except Exception:
        return ""


def _record_web_login(tid, profile, auth_session):
    """Records one verified Twitch OAuth login per Streamlit session."""
    marker = f"_sd_web_login_recorded_{tid}"
    session_stamp = str(auth_session or "")
    if not session_stamp or st.session_state.get(marker) == session_stamp:
        return
    st.session_state[marker] = session_stamp
    now_ms = int(time.time() * 1000)
    login = str((profile or {}).get("login") or "")[:100]
    display_name = str((profile or {}).get("display_name") or login or tid)[:100]

    def _bump(current):
        current = dict(current) if isinstance(current, dict) else {}
        try:
            count = max(0, int(current.get("login_count") or 0))
        except (TypeError, ValueError):
            count = 0
        return {
            "login": login, "display_name": display_name,
            "first_login_ms": int(current.get("first_login_ms") or now_ms),
            "last_login_ms": now_ms, "login_count": count + 1,
        }

    try:
        db.reference(f"streamdex_web_auth/{tid}").transaction(_bump)
    except Exception:
        # Analytics must never prevent sign-in if Firebase is temporarily unavailable.
        pass


def _record_tool_use(tid, tool):
    """Records direct page opens only; Streamlit renders inactive tabs too."""
    if st.session_state.get("auth_method") != "twitch":
        return
    auth_session = str(st.session_state.get("authenticated_at") or "")
    marker = f"_sd_tool_visit_recorded_{tid}_{tool}_{auth_session}"
    if st.session_state.get(marker):
        return
    st.session_state[marker] = True
    now_ms = int(time.time() * 1000)

    def _bump(current):
        current = dict(current) if isinstance(current, dict) else {}
        try:
            visits = max(0, int(current.get("visit_count") or 0))
        except (TypeError, ValueError):
            visits = 0
        return {
            "tool": str(tool)[:80],
            "first_used_ms": int(current.get("first_used_ms") or now_ms),
            "last_used_ms": now_ms, "visit_count": visits + 1,
        }

    try:
        db.reference(f"streamdex_tool_usage/{tid}/{tool}").transaction(_bump)
    except Exception:
        pass


def _fmt_ago(ms):
    if not ms:
        return "nie"
    diff = max(0, int((time.time() * 1000 - int(ms)) / 1000))
    if diff < 60:
        return f"vor {diff} s"
    if diff < 3600:
        return f"vor {diff // 60} min"
    if diff < 86400:
        return f"vor {diff // 3600} h"
    return f"vor {diff // 86400} d"


TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{32}$")   # genau das Format, das die App erzeugt (token_urlsafe(24))
TID_RE = re.compile(r"^[0-9]{1,15}$")
TOKEN_MAX_AGE_MS = 5 * 60 * 1000
SESSION_MAX_AGE_S = 2 * 60 * 60   # nach 2 Stunden ist ein neuer Login über die App nötig

def has_active_streamer_login():
    """True, wenn eine bestätigte Streamer-Sitzung existiert und das Zwei-Stunden-Limit nicht abgelaufen ist."""
    tid = str(st.session_state.get("authenticated_tid") or "")
    if not TID_RE.fullmatch(tid):
        return False
    try:
        started = float(st.session_state.get("authenticated_at") or 0)
    except (TypeError, ValueError):
        return False
    age = time.time() - started
    return started > 0 and 0 <= age <= SESSION_MAX_AGE_S


# Twitch OAuth wird direkt abgewickelt, weil Streamlit's st.login() bei dieser
# Twitch-Konfiguration den Callback mit leeren userinfo-Daten beendet.
TWITCH_REDIRECT_URI = "https://streamdex.streamlit.app/"
TWITCH_AUTHORIZE_URL = "https://id.twitch.tv/oauth2/authorize"
TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
TWITCH_VALIDATE_URL = "https://id.twitch.tv/oauth2/validate"
TWITCH_USERS_URL = "https://api.twitch.tv/helix/users"
TWITCH_STATE_MAX_AGE_S = 10 * 60
TWITCH_BROWSER_COOKIE = "streamdex_oauth_browser"


def _oauth_browser_binding_status():
    """Return (controller_ready, browser binding); cookie is browser-local, not session-local."""
    try:
        controller = CookieController(key="streamdex_oauth_cookie_controller")
        cookies = controller.getAll()
    except Exception:
        return False, None
    if cookies is None:
        return False, None
    value = cookies.get(TWITCH_BROWSER_COOKIE) if isinstance(cookies, dict) else None
    if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{32,100}", value):
        return True, value
    return True, None


def _ensure_oauth_browser_binding():
    """Create a short-lived, random browser cookie before showing the OAuth link."""
    ready, binding = _oauth_browser_binding_status()
    if not ready:
        return None
    if binding:
        return binding
    try:
        controller = CookieController(key="streamdex_oauth_cookie_controller")
        controller.set(
            TWITCH_BROWSER_COOKIE,
            secrets.token_urlsafe(32),
            max_age=TWITCH_STATE_MAX_AGE_S,
            secure=True,
            same_site="lax",
        )
    except Exception as exc:
        print(f"[dashboard] OAuth browser cookie setup failed ({safe_exception_label(exc)})")
    return None


def _oauth_browser_binding_key(binding):
    return hashlib.sha256(str(binding).encode("utf-8")).hexdigest()


def _twitch_credentials():
    """Liest Client-ID und Client-Secret aus [twitch] oder [auth.twitch]."""
    candidates = []
    try:
        candidates.append(st.secrets["twitch"])
    except Exception:
        pass
    try:
        candidates.append(st.secrets["auth"]["twitch"])
    except Exception:
        pass

    for section in candidates:
        client_id = str(section.get("client_id", "") or "").strip()
        client_secret = str(section.get("client_secret", "") or "").strip()
        if client_id and client_secret:
            return client_id, client_secret

    raise ValueError(
        "Twitch-Zugangsdaten fehlen. In Streamlit Secrets muss [twitch] oder "
        "[auth.twitch] jeweils client_id und client_secret enthalten."
    )


def _make_twitch_state(client_secret):
    """Erzeugt einen zeitlich begrenzten, signierten OAuth-state-Wert."""
    return make_signed_oauth_state(client_secret)


def _valid_twitch_state(state, client_secret):
    """Prüft Signatur und Ablaufzeit des OAuth-state-Werts."""
    return verify_signed_oauth_state(
        state, client_secret, max_age_seconds=TWITCH_STATE_MAX_AGE_S
    )


def _register_twitch_state(state, browser_binding):
    """Store only state and browser-binding digests; never persist raw values."""
    now_ms = int(time.time() * 1000)
    root = db.reference("streamdex_oauth_states")
    records = root.get() or {}
    if isinstance(records, dict):
        for key, record in list(records.items()):
            if not oauth_state_record_is_active(record, now_ms):
                try:
                    root.child(str(key)).delete()
                except Exception:
                    pass
    digest = oauth_state_key(state)
    root.child(digest).set({
        "browser_binding_hash": _oauth_browser_binding_key(browser_binding),
        "issued_at_ms": now_ms,
        "expires_at_ms": now_ms + TWITCH_STATE_MAX_AGE_S * 1000,
        "consumed": False,
    })


def _consume_twitch_state(state, browser_binding):
    """Atomically consume state only from the browser that initiated OAuth."""
    digest = oauth_state_key(state)
    ref = db.reference(f"streamdex_oauth_states/{digest}")
    outcome = {"accepted": False}
    now_ms = int(time.time() * 1000)

    def consume(current):
        outcome["accepted"] = False
        if not oauth_state_record_is_active(current, now_ms):
            return current
        if not hmac.compare_digest(
            str(current.get("browser_binding_hash") or ""),
            _oauth_browser_binding_key(browser_binding),
        ):
            return current
        outcome["accepted"] = True
        updated = dict(current)
        updated["consumed"] = True
        updated["consumed_at_ms"] = now_ms
        return updated

    try:
        ref.transaction(consume)
    except Exception:
        return False
    if outcome["accepted"]:
        try:
            ref.delete()
        except Exception:
            pass
    return bool(outcome["accepted"])


def _twitch_authorization_url(browser_binding):
    """Liefert eine OAuth-URL, gebunden an den Browser-Cookie."""
    if not isinstance(browser_binding, str) or not re.fullmatch(r"[A-Za-z0-9_-]{32,100}", browser_binding):
        return None, "Die Browser-Sitzung wird vorbereitet. Bitte warte kurz und versuche es erneut."
    try:
        client_id, client_secret = _twitch_credentials()
    except ValueError as exc:
        return None, str(exc)

    state = _make_twitch_state(client_secret)
    try:
        _register_twitch_state(state, browser_binding)
    except Exception as exc:
        print(f"[dashboard] OAuth state registration failed ({safe_exception_label(exc)})")
        return None, "Die Twitch-Anmeldung ist gerade nicht verfügbar. Bitte versuche es später erneut."
    params = {
        "client_id": client_id,
        "redirect_uri": TWITCH_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid moderator:read:followers channel:read:subscriptions bits:read channel:read:goals channel:read:hype_train channel:read:ads channel:read:polls channel:read:predictions channel:read:charity channel:manage:schedule",
        "state": state,
    }
    return f"{TWITCH_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}", None


def _twitch_http_json(url, method="GET", form=None, headers=None):
    """Sendet eine Twitch-HTTP-Anfrage und liefert JSON ohne Tokens in Fehlermeldungen."""
    data = urllib.parse.urlencode(form).encode("utf-8") if form is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        headers=headers or {},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Twitch antwortet mit HTTP {exc.code}.") from None
    except urllib.error.URLError:
        raise RuntimeError("Twitch ist vorübergehend nicht erreichbar.") from None
    except TimeoutError:
        raise RuntimeError("Die Verbindung zu Twitch hat zu lange gedauert.") from None

    try:
        result = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RuntimeError("Twitch hat eine ungültige Antwort gesendet.") from None
    if not isinstance(result, dict):
        raise RuntimeError("Twitch hat eine unerwartete Antwort gesendet.")
    return result


def handle_twitch_oauth_callback():
    """Verarbeitet einen Twitch-Callback; OAuth-state ist signiert, kurzlebig und einmalig."""
    has_code = "code" in st.query_params
    has_error = "error" in st.query_params
    if not has_code and not has_error:
        return False

    cookie_ready, browser_binding = _oauth_browser_binding_status()
    if not cookie_ready:
        # Keep callback parameters until the cookie component has hydrated and rerun.
        return False

    code = str(st.query_params.get("code", "") or "").strip()
    state = str(st.query_params.get("state", "") or "").strip()
    provider_error = str(st.query_params.get("error", "") or "").strip()

    def _return_to_dashboard(notice=None):
        if notice:
            st.session_state["twitch_login_notice"] = notice
        st.query_params.clear()
        st.query_params["dashboard"] = "1"
        return True

    try:
        client_id, client_secret = _twitch_credentials()
        if not state or not _valid_twitch_state(state, client_secret):
            return _return_to_dashboard(
                "Der Twitch-Anmeldelink ist abgelaufen oder ungültig. Bitte starte die Anmeldung erneut."
            )
        if not browser_binding or not _consume_twitch_state(state, browser_binding):
            return _return_to_dashboard(
                "Dieser Twitch-Anmeldelink wurde bereits verwendet oder ist abgelaufen. Bitte starte die Anmeldung erneut."
            )

        if provider_error:
            if provider_error == "access_denied":
                return _return_to_dashboard("Du hast die Anmeldung bei Twitch abgebrochen.")
            return _return_to_dashboard(
                "Twitch hat die Anmeldung abgelehnt. Bitte starte sie erneut."
            )
        if not code:
            return _return_to_dashboard(
                "Der Twitch-Rückweg war unvollständig. Bitte starte die Anmeldung erneut."
            )

        token_data = _twitch_http_json(
            TWITCH_TOKEN_URL,
            method="POST",
            form={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": TWITCH_REDIRECT_URI,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        access_token = str(token_data.get("access_token", "") or "")
        if not access_token:
            raise RuntimeError("Missing token")

        validation = _twitch_http_json(
            TWITCH_VALIDATE_URL,
            headers={"Authorization": f"OAuth {access_token}"},
        )
        if str(validation.get("client_id", "")) != client_id:
            raise RuntimeError("Token application mismatch")

        twitch_id = str(validation.get("user_id", "") or "")
        if not TID_RE.fullmatch(twitch_id):
            raise RuntimeError("Invalid Twitch user ID")

        user_data = _twitch_http_json(
            TWITCH_USERS_URL,
            headers={
                "Client-Id": client_id,
                "Authorization": f"Bearer {access_token}",
            },
        )
        users = user_data.get("data", [])
        if not isinstance(users, list) or not users or not isinstance(users[0], dict):
            raise RuntimeError("Missing Twitch profile")

        user = users[0]
        if str(user.get("id", "")) != twitch_id:
            raise RuntimeError("Twitch profile ID mismatch")

        # Start a fresh authenticated session, never reuse an earlier account's tokens.
        _clear_oauth_tokens()
        st.session_state["authenticated_tid"] = twitch_id
        st.session_state["authenticated_at"] = time.time()
        st.session_state["auth_method"] = "twitch"
        st.session_state["twitch_profile"] = {
            "id": twitch_id,
            "login": str(user.get("login", "") or "")[:100],
            "display_name": str(user.get("display_name", "") or user.get("login", "") or twitch_id)[:100],
            "picture": str(user.get("profile_image_url", "") or "")[:1000],
        }
        # Tokens remain only in this server-side Streamlit session.
        st.session_state["twitch_oauth_tid"] = twitch_id
        st.session_state["twitch_oauth_access_token"] = access_token
        st.session_state["twitch_oauth_refresh_token"] = str(token_data.get("refresh_token", "") or "")
        try:
            expires_in = max(60, min(int(token_data.get("expires_in") or 14400), 86400))
        except (TypeError, ValueError):
            expires_in = 14400
        st.session_state["twitch_oauth_expires_at"] = time.time() + expires_in
        granted_scopes = token_data.get("scope", [])
        st.session_state["twitch_oauth_scopes"] = list(granted_scopes) if isinstance(granted_scopes, list) else []
        st.session_state.pop("dashboard_reauth_required", None)
        st.session_state.pop("session_expired", None)
        st.session_state.pop("twitch_login_notice", None)
        return _return_to_dashboard()

    except Exception as exc:
        # Never show exception details, provider response bodies, or tokens in the browser/log.
        print(f"[dashboard] Twitch OAuth callback failed ({safe_exception_label(exc)})")
        return _return_to_dashboard(
            "Die Twitch-Anmeldung konnte nicht abgeschlossen werden. Bitte starte die Anmeldung erneut."
        )


def _clear_oauth_tokens():
    """Clear all Twitch OAuth credentials and scopes from the server-side session."""
    for key in (
        "twitch_oauth_tid", "twitch_oauth_access_token", "twitch_oauth_refresh_token",
        "twitch_oauth_expires_at", "twitch_oauth_scopes",
    ):
        st.session_state.pop(key, None)


def _clear_authenticated_session():
    """Logout/expiry cleanup; session credentials must not survive authentication changes."""
    _clear_oauth_tokens()
    for key in (
        "authenticated_tid", "authenticated_at", "auth_method", "twitch_profile",
        "acct_data", "dashboard_reauth_required", "sd_wheel_result",
    ):
        st.session_state.pop(key, None)


def _render_twitch_login():
    """Startet den zuverlässigen Twitch-OAuth-Link für Streamlit Cloud."""
    browser_binding = _ensure_oauth_browser_binding()
    if not browser_binding:
        st.info("Browser-Sitzung wird vorbereitet. Falls die Anmeldung nicht erscheint, lade die Seite bitte einmal neu.")
        return
    url, error = _twitch_authorization_url(browser_binding)
    if error:
        st.error(error)
        st.info("In Streamlit Secrets müssen die Twitch-Zugangsdaten unter [twitch] mit client_id und client_secret stehen.")
        return

    # Streamlit Cloud kann Top-Level-Navigation aus der eingebetteten App-Ansicht
    # blockieren. Der native Link-Button öffnet externe OAuth-Seiten zuverlässig in
    # einem neuen Tab; danach leitet der Callback wieder auf /?dashboard=1.
    st.link_button(
        "🟣 Mit Twitch anmelden",
        url,
        type="primary",
        use_container_width=True,
    )



def _verify_and_consume_token(token: str):
    """Prüft einen Login-Token und löscht ihn atomar (Einmal-Nutzung).
    Gibt die Twitch-ID zurück oder None. Der Grund einer Ablehnung wird nur auf der Serverkonsole geloggt."""
    def _fail(category):
        # Keep diagnostics categorical: never log the supplied token or database payload.
        print(f"[dashboard] Einmal-Token abgelehnt ({category})")
        return None

    if not isinstance(token, str) or not TOKEN_RE.fullmatch(token):
        return _fail("invalid_format")

    consumed = {}

    def _take(current):
        # firebase_admin erlaubt in transaction() KEIN None als Ergebnis ("Value must not be none").
        # Deshalb wird der Eintrag atomar auf eine Markierung gesetzt; nur wer noch die echten Daten
        # (ohne "used") sieht, hat den Token eingelöst. Danach wird der Knoten gelöscht.
        if isinstance(current, dict) and not current.get("used"):
            consumed["data"] = current
        else:
            consumed["data"] = None
        return {"used": True}

    ref = db.reference(f"dash_tokens/{token}")
    try:
        ref.transaction(_take)
    except Exception as exc:
        return _fail(f"transaction_error:{safe_exception_label(exc)}")
    try:
        ref.delete()   # Markierung entfernen (Token ist ohnehin schon unbrauchbar)
    except Exception:
        pass

    data = consumed.get("data")
    if not isinstance(data, dict):
        return _fail("not_found_or_already_used")

    try:
        created_at = int(data.get("ts") or 0)
    except (TypeError, ValueError):
        return _fail("invalid_timestamp")
    age_ms = int(time.time() * 1000) - created_at
    if not created_at or age_ms < -60_000 or age_ms > TOKEN_MAX_AGE_MS:
        return _fail("expired_or_invalid_timestamp")

    tid = str(data.get("tid") or "")
    if not TID_RE.fullmatch(tid):
        return _fail("invalid_user_id")
    return tid


def cleanup_old_entries(token_max_age_hours=1, history_days=400):
    """Admin-Aufräumen (im Admin-Panel per Knopf aufrufen):
    - dash_tokens: abgelaufene und halb eingelöste Einträge entfernen
    - stats_history: Tageseinträge älter als history_days entfernen
    Gibt {"tokens": n, "history_days": n} zurück."""
    now_ms = int(time.time() * 1000)
    removed_tokens = removed_days = 0

    try:
        tokens = db.reference("dash_tokens").get() or {}
    except Exception:
        tokens = {}
    if isinstance(tokens, dict):
        for key, val in list(tokens.items()):
            try:
                ts = int(val.get("ts") or 0) if isinstance(val, dict) else 0
            except (TypeError, ValueError):
                ts = 0
            if not ts or now_ms - ts > token_max_age_hours * 3600 * 1000:
                try:
                    db.reference(f"dash_tokens/{key}").delete()
                    removed_tokens += 1
                except Exception:
                    pass

    cutoff = (datetime.now(TZ).date() - timedelta(days=history_days)).isoformat()
    try:
        tids = list((db.reference("stats_history").get(shallow=True) or {}).keys())
    except Exception:
        tids = []
    for tid in tids:
        try:
            days = list((db.reference(f"stats_history/{tid}").get(shallow=True) or {}).keys())
        except Exception:
            continue
        for day in days:
            if re.match(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$", str(day)) and str(day) < cutoff:
                try:
                    db.reference(f"stats_history/{tid}/{day}").delete()
                    removed_days += 1
                except Exception:
                    pass
    return {"tokens": removed_tokens, "history_days": removed_days}


def _load_messages(tid):
    data = db.reference(f"chats/{tid}/messages").order_by_child("ts").limit_to_last(100).get() or {}
    msgs = [dict(v, id=k) for k, v in data.items() if isinstance(v, dict)]
    msgs.sort(key=lambda m: (int(m.get("ts") or 0), m["id"]))
    return msgs


def _send_message(tid, name, text):
    text = text.strip()[:2000]
    if not text:
        return
    db.reference(f"chats/{tid}/messages").push({"sender": "streamer", "name": name, "text": text, "ts": SERVER_TS})
    db.reference(f"chat_meta/{tid}").update({"last_ts": SERVER_TS, "last_sender": "streamer", "last_text": text[:100]})


def _support_last_read(tid):
    """Zeitstempel (ms) der zuletzt als gelesen markierten Support-Antwort. Liegt unter support_read/{tid}."""
    try:
        return int(db.reference(f"support_read/{tid}").get() or 0)
    except Exception:
        return 0


def _unread_admin(msgs, last_read):
    """Antworten vom Support, die neuer sind als der Gelesen-Stand."""
    out = []
    for m in msgs:
        try:
            ts = int(m.get("ts") or 0)
        except (TypeError, ValueError):
            ts = 0
        if m.get("sender") == "admin" and ts > last_read:
            out.append(m)
    return out


def _mark_support_read(tid, msgs):
    """Markiert alles bis zur neuesten bekannten Support-Antwort als gelesen. Bewusst NICHT die aktuelle Zeit:
    sonst würde eine Antwort, die gerade erst eingetroffen ist, ungesehen als gelesen gelten."""
    latest = 0
    for m in msgs:
        if m.get("sender") == "admin":
            try:
                latest = max(latest, int(m.get("ts") or 0))
            except (TypeError, ValueError):
                pass
    if latest:
        try:
            db.reference(f"support_read/{tid}").set(latest)
        except Exception:
            pass


# ----------------------------------------------------------------------------
# 🏠 Übersicht (echte Daten aus Firebase: presence, stats, game_flags, shop/beta)
# Hinweis: Live-Zuschauer und Coins im Umlauf werden von der App aktuell nicht
# nach Firebase gemeldet und deshalb bewusst NICHT angezeigt (keine Dummy-Werte).
# ----------------------------------------------------------------------------
OVERVIEW_CSS = """<style>
.sdx-grid4{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,220px),1fr));gap:14px;margin:6px 0 18px}
.sdx-grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr));gap:14px;margin-bottom:16px}
.sdx-metric,.sdx-card{position:relative;overflow:hidden;background:linear-gradient(145deg,rgba(15,23,42,.96),rgba(11,18,35,.94));border:1px solid rgba(148,163,184,.16);border-radius:18px;padding:18px;box-shadow:0 12px 32px rgba(0,0,0,.2);transition:transform .18s ease,border-color .18s ease,box-shadow .18s ease}
.sdx-metric:before{content:"";position:absolute;inset:0 0 auto;height:2px;background:linear-gradient(90deg,#a855f7,#06b6d4);opacity:.9}
.sdx-metric:hover,.sdx-card:hover{transform:translateY(-2px);border-color:rgba(168,85,247,.34);box-shadow:0 16px 38px rgba(0,0,0,.28)}
.sdx-label{font-family:'JetBrains Mono',monospace;font-size:.68rem;color:#94a3b8;text-transform:uppercase;letter-spacing:.09em}
.sdx-value{font-size:clamp(1.45rem,2.4vw,1.9rem);line-height:1.2;font-weight:800;letter-spacing:-.04em;margin-top:8px;color:#f8fafc;overflow-wrap:anywhere}
.sdx-sub{font-size:.78rem;line-height:1.5;color:#94a3b8;margin-top:6px}
.sdx-ok{color:#4ade80}.sdx-off{color:#94a3b8}
.sdx-title{display:flex;align-items:center;gap:8px;font-size:1rem;font-weight:800;margin-bottom:14px;color:#f8fafc;letter-spacing:-.02em}
.sdx-bar-row{margin:13px 0}
.sdx-bar-head{display:flex;justify-content:space-between;gap:12px;font-size:.82rem;color:#cbd5e1;margin-bottom:6px}
.sdx-bar-head span:last-child{font-family:'JetBrains Mono',monospace;color:#f8fafc}
.sdx-bar{height:7px;border-radius:99px;background:rgba(148,163,184,.12);overflow:hidden}
.sdx-bar>div{height:100%;border-radius:99px;background:linear-gradient(90deg,#a855f7,#22d3ee);box-shadow:0 0 12px rgba(168,85,247,.25)}
.sdx-chips{display:flex;flex-wrap:wrap;gap:8px}
.sdx-chip{display:inline-flex;align-items:center;gap:5px;padding:6px 10px;border-radius:99px;font-size:.75rem;font-weight:700;border:1px solid rgba(148,163,184,.16);background:rgba(15,23,42,.55)}
.sdx-chip.on{color:#86efac;background:rgba(34,197,94,.08);border-color:rgba(34,197,94,.24)}
.sdx-chip.off{color:#cbd5e1;background:rgba(148,163,184,.06);border-color:rgba(148,163,184,.15)}
.sdx-kv{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;padding:10px 0;border-bottom:1px solid rgba(148,163,184,.12);font-size:.83rem;color:#f8fafc}
.sdx-kv span:first-child{color:#94a3b8;flex:1}.sdx-kv span:last-child{text-align:right;overflow-wrap:anywhere;max-width:62%}
.sdx-kv:last-child{border-bottom:0}.sdx-empty{font-size:.85rem;color:#94a3b8;padding:8px 0}
@media(max-width:640px){.sdx-metric,.sdx-card{padding:15px;border-radius:15px}.sdx-grid2{grid-template-columns:minmax(0,1fr)}.sdx-value{font-size:1.55rem}}
</style>"""

ACTIVITY_KEYS = ["checkins", "slot_spins", "megaslot_spins", "fish_catches", "harvests", "raids", "viewers"]


def _num(v):
    try:
        return max(0, int(float(v)))
    except Exception:
        return 0


def _de(n):
    return f"{n:,}".replace(",", ".")


def _overview_html(presence, stats, games, have_games, beta_info, is_online):
    """Baut das Übersichts-HTML. Alles Dynamische wird escaped; bewusst ohne Zeilenumbrüche/Einrückung,
    damit Streamlit-Markdown den Block nicht als Code interpretiert."""
    e = html.escape
    g_total = _num(stats.get("giveaways"))
    g_part = _num(stats.get("giveaway_participants"))
    n_unlocked = len([g for g in games if g in have_games])
    avg = f"Ø {round(g_part / g_total)} pro Giveaway" if g_total else "noch keine Giveaways"

    def metric(label, value, sub="", cls=""):
        sub_html = f'<div class="sdx-sub">{e(sub)}</div>' if sub else ""
        return (f'<div class="sdx-metric"><div class="sdx-label">{e(label)}</div>'
                f'<div class="sdx-value {cls}">{e(value)}</div>{sub_html}</div>')

    metrics = "".join([
        metric("Status", "🟢 Online" if is_online else "⚪ Offline",
               f"Aktiv {_fmt_ago(presence.get('last_seen'))}", "sdx-ok" if is_online else "sdx-off"),
        metric("Giveaways", _de(g_total),
               f"{_de(_num(stats.get('giveaways_7d')))} in 7 Tagen · {_de(_num(stats.get('giveaways_30d')))} in 30 Tagen"),
        metric("Teilnahmen", _de(g_part), avg),
        metric("Freigeschaltete Games", f"{n_unlocked} / {len(games)}",
               "alle frei" if n_unlocked == len(games) else f"{len(games) - n_unlocked} noch gesperrt"),
    ])

    # Aktivitäts-Balken (relativ zum größten Wert)
    rows = [(STAT_KEYS.get(k, k), _num(stats.get(k))) for k in ACTIVITY_KEYS]
    top = max([v for _, v in rows] + [0])
    if top == 0:
        bars = '<div class="sdx-empty">Noch keine Aktivität erfasst.</div>'
    else:
        bars = "".join(
            f'<div class="sdx-bar-row"><div class="sdx-bar-head"><span>{e(label)}</span><span>{_de(v)}</span></div>'
            f'<div class="sdx-bar"><div style="width:{max(2, round(v / top * 100)) if v else 0}%"></div></div></div>'
            for label, v in rows)
    activity = f'<div class="sdx-card"><div class="sdx-title">📈 Aktivität</div>{bars}</div>'

    def kv(k, v):
        return f'<div class="sdx-kv"><span>{e(k)}</span><span>{e(str(v))}</span></div>'

    account_rows = [
        kv("Twitch-Name", presence.get("twitch_username", "?")),
        kv("App-Version", presence.get("app_version", "?")),
        kv("Beta-Status", "🧪 Aktiv" if beta_info else "Nein"),
        kv("Statistik aktualisiert", _fmt_ago(stats.get("updated_at"))),
    ]
    if is_online and presence.get("session_start"):
        account_rows.append(kv("Online seit", _fmt_ts(presence.get("session_start"))))
    account = f'<div class="sdx-card"><div class="sdx-title">🧾 Konto</div>{"".join(account_rows)}</div>'

    chips = "".join(
        f'<span class="sdx-chip {"on" if g_key in have_games else "off"}">'
        f'{"✅" if g_key in have_games else "🔒"} {e(g_name)}</span>'
        for g_key, g_name in games.items())
    games_card = f'<div class="sdx-card"><div class="sdx-title">🎮 Deine Games</div><div class="sdx-chips">{chips}</div></div>'

    return f'<div class="sdx-grid4">{metrics}</div><div class="sdx-grid2">{activity}{account}</div>{games_card}'


# ----------------------------------------------------------------------------
# 📅 Verlauf: tägliche Zuwächse aus den Tagesständen stats_history/{tid}/{YYYY-MM-DD}
# (die App speichert dort einmal pro Tag den letzten Stand der kumulativen Zähler)
# ----------------------------------------------------------------------------
HISTORY_LABELS = {
    "giveaways": "Giveaways",
    "giveaway_participants": "Teilnahmen",
    "viewers": "Neue Viewer",
    "checkins": "Check-ins",
    "slot_spins": "Slot-Spins",
    "megaslot_spins": "Mega-Slot-Spins",
    "raids": "Raids",
    "fish_catches": "Fänge (Angeln)",
    "harvests": "Ernten (Farm)",
}


@st.cache_data(ttl=120, show_spinner=False)
def _load_history(tid):
    """Letzte ~120 Tagesstände (Schlüssel = Datum, sortiert sich von selbst). Einer mehr als der größte Zeitraum dient als Basis."""
    data = db.reference(f"stats_history/{tid}").order_by_key().limit_to_last(121).get() or {}
    return data if isinstance(data, dict) else {}


def _daily_series(history, key, days, today=None):
    """Tägliche Zuwächse eines kumulativen Zählers als pandas-Serie (lückenlos, fehlende Tage = 0).
    Basis ist der höchste bisher gesehene Stand: so erzeugt ein Ausreißer nach unten (z.B. leere lokale DB)
    keine falschen Spitzen. Tage ohne App-Start werden dem nächsten Tag mit Daten zugerechnet."""
    today = today or datetime.now(TZ).date()
    deltas, base = {}, None
    for day in sorted(history):
        entry = history[day]
        if not isinstance(entry, dict):
            continue
        try:
            d = datetime.strptime(day, "%Y-%m-%d").date()
        except ValueError:
            continue
        val = _num(entry.get(key))
        if base is not None and val > base:
            deltas[d] = val - base
        base = val if base is None else max(base, val)
    idx = pd.date_range(today - timedelta(days=days - 1), today)
    return pd.Series([deltas.get(i.date(), 0) for i in idx], index=idx, name=HISTORY_LABELS.get(key, key))


# ----------------------------------------------------------------------------
# 🧾 Konto & Datenschutz: Daten ansehen, exportieren, Konto-Daten löschen
# ----------------------------------------------------------------------------
# Wird beim Löschen entfernt (alles, was unter der eigenen Twitch-ID liegt). presence ZULETZT,
# damit der Login bei einem Fehler mittendrin noch funktioniert und man es erneut versuchen kann.
_DELETE_PATHS = [
    "stats/{t}", "stats_history/{t}", "chats/{t}", "chat_meta/{t}", "gifts/{t}",
    "lurk/stats/{t}", "lurk/chats/{t}", "lurk/chat_meta/{t}", "lurk/presence/{t}",
    "support_read/{t}", "giveaway_log/{t}",
    "radar_watchlists/{t}", "radar_analytics/{t}", "streamdex_planner/{t}",
    "streamdex_ideas/{t}", "streamdex_brackets/{t}", "streamdex_wheel/{t}",
    "streamdex_goals/{t}", "streamdex_modlog/{t}", "streamdex_modteam/{t}",
    "streamdex_clips/{t}", "streamdex_web_auth/{t}", "streamdex_tool_usage/{t}",
    "creator_profiles/{t}", "presence/{t}",
]
# Kauf-/Freischaltungsdaten bleiben bewusst erhalten.
_KEEP_PATHS = ["tour_skip/{t}", "shop/beta/{t}", "game_flags/streamers/{t}"]
_SHARED_ACCOUNT_ROOTS = (
    "feedback_inbox",
    "streamdex_community_wishlist",
    "community_polls",
    "streamdex_quiz_rooms",
    "streamdex_events",
)

ACCOUNT_DATA_TABLE = """
| Was | Wozu |
|---|---|
| Twitch-ID, Benutzername, App-Version, Online-Status, letzte Aktivität und Website-Login-Zeitpunkte | Login, Status-Anzeige und Zuordnung deiner Daten |
| Direkte Tool-Aufrufe und gespeicherte Einträge der StreamDex-Werkzeuge | Nutzungsübersicht und persönliche Werkzeuge |
| Zähler (Giveaways, Check-ins, Spins, …), Tagesstände und Giveaway-Verlauf | Statistiken im Dashboard |
| Eigene Feedback-Beiträge, Community-Wünsche, Umfragen, Quiz-Antworten und Event-Anmeldungen | Community-Funktionen |
| Support-Nachrichten und Feedback | Support |
| Kauf- und Freischaltungsdaten | Games und Features, die du freigeschaltet hast; bleiben bei Datenlöschung erhalten |
| Lokal gespeicherte Einstellungen und Logs deiner Desktop-App | Werden nicht auf dem StreamDex-Webserver gespeichert |
"""


def _account_area_label(path):
    """Human-readable names for data-access and deletion error messages."""
    root = str(path or "").strip("/").split("/", 1)[0]
    labels = {
        "stats": "StreamDex-Statistiken",
        "stats_history": "Statistik-Verlauf",
        "chats": "Chat-Nachrichten",
        "chat_meta": "Chat-Metadaten",
        "gifts": "Geschenke",
        "lurk": "Lurk-Daten",
        "support_read": "Support-Lesestatus",
        "giveaway_log": "Giveaway-Verlauf",
        "radar_watchlists": "Radar-Watchlist",
        "radar_analytics": "Insight-Verläufe",
        "streamdex_planner": "Planner-Termine",
        "streamdex_ideas": "StreamDex-Ideen",
        "streamdex_brackets": "Turnierdaten",
        "streamdex_wheel": "Glücksrad-Daten",
        "streamdex_goals": "Ziele",
        "streamdex_modlog": "Moderationsprotokoll",
        "streamdex_modteam": "Moderationsteam",
        "streamdex_clips": "Clip-Sammlung",
        "streamdex_web_auth": "Web-Anmeldedaten",
        "streamdex_tool_usage": "Nutzungsstatistiken",
        "presence": "Online-Status",
        "creator_profiles": "Creator-Profil",
        "creator_profile_slugs": "öffentlicher Profil-Link",
        "streamdex_events": "Community-Events",
        "feedback_inbox": "Feedback-Einträge",
        "streamdex_community_wishlist": "Community-Wünsche",
        "community_polls": "Community-Umfragen",
        "streamdex_quiz_rooms": "Quizräume und Antworten",
    }
    return labels.get(root, "Datenbereich")


def _safe_get(path, errors=None):
    try:
        return db.reference(path).get()
    except Exception:
        if errors is not None:
            message = f"{_account_area_label(path)} konnten nicht gelesen werden."
            if message not in errors:
                errors.append(message)
            return None
        return {"_fehler": "Datenbereich konnte nicht gelesen werden."}


def _build_account_export_json(tid, data, exported_at=None):
    """Build the account JSON export in one testable, deterministic place."""
    if not is_valid_twitch_id(tid):
        raise ValueError("Ungültige Twitch-ID für den Datenexport.")
    payload = {
        "exportiert_am": exported_at or datetime.now(TZ).isoformat(timespec="seconds"),
        "twitch_id": str(tid),
        "hinweis": "Zeitstempel (ts, last_seen, …) sind Millisekunden seit 1970 (UTC).",
        "daten": data if isinstance(data, dict) else {},
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def _load_feedback(tid):
    """Load all feedback entries belonging to this account, not only the latest page."""
    data = db.reference("feedback_inbox").get() or {}
    if not isinstance(data, dict):
        return {}
    return {
        key: value for key, value in data.items()
        if isinstance(value, dict) and str(value.get("tid") or "") == str(tid)
    }


def _read_shared_account_roots(errors=None):
    """Load the shared collections needed to export/delete this account's own contributions."""
    roots = {}
    errors = errors if errors is not None else []
    for path in _SHARED_ACCOUNT_ROOTS:
        try:
            value = db.reference(path).get() or {}
            roots[path] = value if isinstance(value, dict) else {}
        except Exception:
            roots[path] = {}
            message = f"{_account_area_label(path)} konnten nicht vollständig geprüft werden."
            if message not in errors:
                errors.append(message)
    return roots


def _collect_account_data(tid, errors=None):
    """Collect private records and only the current user's contribution to shared collections."""
    tid = str(tid or "")
    if not is_valid_twitch_id(tid):
        raise ValueError("Ungültige Twitch-ID für den Datenexport.")
    errors = errors if errors is not None else []
    out = {}
    for path in _KEEP_PATHS + _DELETE_PATHS:
        p = path.format(t=tid)
        val = _safe_get(p, errors=errors)
        if val not in (None, {}, []):
            out[p] = val

    profile = out.get(f"creator_profiles/{tid}")
    old_slug = str(profile.get("slug") or "") if isinstance(profile, dict) else ""
    if re.fullmatch(r"[a-z0-9][a-z0-9-]{2,39}", old_slug):
        slug_owner = _safe_get(f"creator_profile_slugs/{old_slug}", errors=errors)
        if str(slug_owner or "") == tid:
            out[f"creator_profile_slugs/{old_slug}"] = tid

    shared_roots = _read_shared_account_roots(errors)
    shared_data = collect_user_shared_data(tid, shared_roots)
    if shared_data:
        out["community_activity (nur deine Beiträge, Stimmen, Antworten und Anmeldungen)"] = shared_data
    return out


def _delete_account_data(tid):
    """Delete only this account's private data and contributions to shared collections."""
    tid = str(tid or "")
    if not is_valid_twitch_id(tid):
        raise ValueError("Ungültige Twitch-ID für die Kontolöschung.")

    removed, errors = 0, []
    # Remove the public slug while the private profile still exists.
    try:
        profile = db.reference(f"creator_profiles/{tid}").get() or {}
        old_slug = str(profile.get("slug") or "") if isinstance(profile, dict) else ""
        if re.fullmatch(r"[a-z0-9][a-z0-9-]{2,39}", old_slug):
            slug_ref = db.reference(f"creator_profile_slugs/{old_slug}")
            if str(slug_ref.get() or "") == tid:
                slug_ref.delete()
                removed += 1
    except Exception:
        errors.append("Dein öffentlicher Profil-Link konnte nicht freigegeben werden.")

    shared_roots = _read_shared_account_roots(errors)
    for target in plan_shared_account_deletions(tid, shared_roots):
        try:
            ref = db.reference(target)
            if ref.get() is not None:
                ref.delete()
                removed += 1
        except Exception:
            errors.append("Community-Beiträge oder eigene Stimmen konnten nicht vollständig gelöscht werden.")

    for path in _DELETE_PATHS:
        p = path.format(t=tid)
        # Presence is deliberately last: keep the account recognizable for a retry if
        # any previous deletion failed. A partial deletion must never look successful.
        if p == f"presence/{tid}" and errors:
            continue
        try:
            ref = db.reference(p)
            if ref.get() is not None:
                ref.delete()
                removed += 1
        except Exception:
            errors.append(f"{_account_area_label(p)} konnten nicht gelöscht werden.")

    return removed, list(dict.fromkeys(errors))

def _render_account_tab(tid, username, is_online):
    st.subheader("🧾 Konto & Datenschutz")
    st.caption("Hier siehst du, welche Daten Streamdex unter deiner Twitch-ID gespeichert hat, kannst sie exportieren "
               "oder löschen.")
    with st.expander("Was wird gespeichert und wozu?"):
        st.markdown(ACCOUNT_DATA_TABLE)

    # --- Daten ansehen & exportieren (wird erst auf Klick geladen) ---
    st.markdown("### 📥 Meine Daten")
    if st.button("Meine Daten laden", key="acct_load"):
        export_errors = []
        account_data = _collect_account_data(tid, errors=export_errors)
        st.session_state["acct_data"] = {"tid": tid, "data": account_data, "errors": export_errors}
    cached = st.session_state.get("acct_data")
    if cached and cached.get("tid") == tid:
        data = cached.get("data") or {}
        export_errors = cached.get("errors") or []
        if export_errors:
            st.warning("Einige Datenbereiche konnten nicht vollständig gelesen werden: " + " ".join(export_errors)
                       + " Bitte prüfe die Firebase-Berechtigungen und lade die Daten erneut.")
        if not data and not export_errors:
            st.info("Unter deiner Twitch-ID sind keine Daten gespeichert.")
        elif data:
            st.download_button(
                "⬇️ Alles als JSON herunterladen",
                data=_build_account_export_json(tid, data),
                file_name=f"streamdex_daten_{tid}.json",
                mime="application/json",
                key="acct_dl",
            )
            for path, val in data.items():
                with st.expander(path):
                    st.json(val)

    st.divider()

    # --- Löschen ---
    st.markdown("### 🗑️ Meine Daten löschen")
    st.warning(
        "Gelöscht werden Status, Statistiken, Verlauf, Support-Chat und deine Feedback-Einträge auf dem Server. "
        "Das lässt sich **nicht rückgängig machen**."
    )
    st.markdown(
        "**Bleibt bestehen:** Kauf- und Freischaltungsdaten (damit bezahlte Games erhalten bleiben), "
        "die Sperrliste (Missbrauchsschutz) und alles, was nur auf deinem PC liegt (Einstellungen, Logs). "
        "Dein Twitch-Konto ist nicht betroffen. Startest du die App danach wieder, legt sie neue Einträge an."
    )
    if is_online:
        st.info("Deine Desktop-App läuft gerade und würde die Daten sofort neu anlegen. "
                "Schließe die App zuerst, warte etwa 3 Minuten, bis dein Status „Offline“ ist, und lade diese Seite neu.")
    confirm = st.checkbox("Ich habe verstanden, dass meine Daten dauerhaft gelöscht werden.", key="acct_confirm")
    typed = st.text_input(f"Zur Bestätigung deinen Twitch-Namen eingeben: **{username}**", key="acct_typed")
    ready = confirm and typed.strip().lower() == str(username).strip().lower() and not is_online
    if st.button("🗑️ Endgültig löschen", type="primary", disabled=not ready, key="acct_delete"):
        removed, errors = _delete_account_data(tid)
        if errors:
            st.error("Die Kontolöschung war unvollständig. Diese Bereiche sind betroffen: "
                     + " ".join(errors) + " Bitte behebe die Firebase-Berechtigungen und starte den Löschvorgang erneut.")
        else:
            st.session_state.pop("authenticated_tid", None)
            st.session_state.pop("acct_data", None)
            st.session_state["acct_deleted"] = removed
            st.rerun()


# ----------------------------------------------------------------------------
# 🔔 Update-Hinweis: App-Version des Streamers mit der neuesten GitHub-Release vergleichen
# ----------------------------------------------------------------------------
GITHUB_REPO = "FreeSchok01/Givewaytool"   # dasselbe Repo, das auch die Desktop-App für Updates nutzt


def _version_tuple(v):
    """Gleiche Logik wie parse_v() in der App: alles außer Ziffern und Punkten entfernen ("BETA VERSION V2" -> (2,))."""
    try:
        return tuple(int(x) for x in re.sub(r"[^0-9.]", "", str(v)).split(".") if x)
    except ValueError:
        return ()


@st.cache_data(ttl=900, show_spinner=False)
def _latest_release():
    """Neueste Release von GitHub (15 Minuten zwischengespeichert, damit das API-Limit nicht erreicht wird)."""
    try:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
            headers={"User-Agent": "StreamdexDashboard", "Accept": "application/vnd.github+json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            d = json.loads(resp.read().decode("utf-8"))
        url = str(d.get("html_url") or "")
        if not url.startswith("https://github.com/"):
            url = f"https://github.com/{GITHUB_REPO}/releases/latest"
        return {"tag": str(d.get("tag_name") or ""), "url": url}
    except Exception:
        return None   # offline, Limit erreicht, kein Release: dann einfach keinen Hinweis zeigen


def _update_notice(app_version):
    """Gibt (neueste_version, link) zurück, wenn eine neuere Version existiert, sonst None."""
    rel = _latest_release()
    if not rel or not rel["tag"]:
        return None
    cur, new = _version_tuple(app_version), _version_tuple(rel["tag"])
    if cur and new and new > cur:
        return rel["tag"], rel["url"]
    return None


# ----------------------------------------------------------------------------
# 🎁 Giveaway-Verlauf (Datum, Preis, Teilnehmerzahl - Gewinnernamen werden bewusst NICHT hochgeladen)
# ----------------------------------------------------------------------------
@st.cache_data(ttl=60, show_spinner=False)
def _load_giveaway_log(tid):
    try:
        data = db.reference(f"giveaway_log/{tid}").get() or {}
    except Exception:
        return []
    if isinstance(data, list):   # Firebase liefert Schlüssel 1,2,3,… als Liste zurück
        data = {str(i): v for i, v in enumerate(data) if v is not None}
    rows = []
    for v in data.values():
        if not isinstance(v, dict):
            continue
        d = str(v.get("date") or "")
        if not re.match(r"^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}$", d):
            continue
        rows.append({"date": d, "Preis": str(v.get("prize") or ""), "Teilnehmer": int(_num(v.get("participants")))})
    rows.sort(key=lambda r: r["date"], reverse=True)
    return rows[:1000]


def _csv_safe(text):
    """Schützt vor Formel-Einschleusung in Excel (Zellen, die mit = + - @ beginnen)."""
    text = str(text)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def _render_giveaway_tab(tid):
    st.subheader("🎁 Giveaway-Verlauf")
    rows = _load_giveaway_log(tid)
    if not rows:
        st.info("Noch kein Giveaway-Verlauf vorhanden. Die App lädt neue und frühere Giveaways alle 10 Minuten hoch "
                "(ältere nach und nach, höchstens 50 pro Durchlauf).")
        return
    df = pd.DataFrame(rows)
    df.insert(0, "Datum", df["date"].map(lambda d: f"{d[8:10]}.{d[5:7]}.{d[0:4]} {d[11:]}"))
    df = df.drop(columns=["date"])
    search = st.text_input("Preis suchen", key="gw_search")
    if search.strip():
        df = df[df["Preis"].str.contains(search.strip(), case=False, regex=False)]
    m1, m2, m3 = st.columns(3)
    m1.metric("Giveaways", _de(len(df)))
    m2.metric("Teilnahmen gesamt", _de(int(df["Teilnehmer"].sum())))
    m3.metric("Ø Teilnehmer", f"{df['Teilnehmer'].mean():.1f}".replace(".", ",") if len(df) else "–")
    st.dataframe(df, use_container_width=True, hide_index=True)
    out = df.copy()
    out["Preis"] = out["Preis"].map(_csv_safe)
    st.download_button("⬇️ Als CSV herunterladen", out.to_csv(index=False, sep=";").encode("utf-8-sig"),
                       file_name="giveaway_verlauf.csv", mime="text/csv", key="gw_csv")
    st.caption("Gewinnernamen werden bewusst nicht ins Dashboard hochgeladen. Sie bleiben nur in deiner App.")


@st.fragment(run_every=60)
def _render_public_live_streamers():
    """Publicly show only accounts whose StreamDex client recently checked in AND whose Twitch channel is live."""
    st.markdown(
        '<section class="sd-public-tools" id="live-streamers">'
        '<div class="sd-public-toolshead"><div><h2>🔴 Gerade live auf StreamDex</h2>'
        '<p>Streamer, deren StreamDex-Tool aktiv verbunden ist und deren Twitch-Stream gerade läuft.</p></div>'
        '<span class="sd-public-count">LIVE</span></div></section>',
        unsafe_allow_html=True,
    )
    try:
        presence = db.reference("presence").get() or {}
        now_ms = int(time.time() * 1000)
        accounts = {}
        if isinstance(presence, dict):
            for tid, record in presence.items():
                if not isinstance(record, dict) or record.get("status") != "online":
                    continue
                try:
                    last_seen = int(record.get("last_seen") or 0)
                except (TypeError, ValueError):
                    continue
                age_ms = now_ms - last_seen
                # Same 150-second heartbeat limit as the admin dashboard.
                if not last_seen or age_ms < -60_000 or age_ms > 150_000:
                    continue
                display_name = str(record.get("twitch_username") or "").strip()
                login = display_name.lower()
                if not re.fullmatch(r"[a-z0-9_]{1,25}", login):
                    continue
                # Use the most recent active presence record if duplicates exist.
                if login not in accounts or last_seen > accounts[login]["last_seen"]:
                    accounts[login] = {
                        "tid": str(tid),
                        "login": login,
                        "name": display_name,
                        "last_seen": last_seen,
                    }
        if not accounts:
            st.info("Noch ist kein StreamDex-Streamer gleichzeitig mit dem Tool verbunden und auf Twitch live.")
            return

        logins = sorted(accounts)[:100]
        client_id, client_secret = _twitch_credentials()
        token_data = _twitch_http_json(
            "https://id.twitch.tv/oauth2/token",
            method="POST",
            form={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "client_credentials",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        app_token = str(token_data.get("access_token") or "")
        if not app_token:
            raise RuntimeError("Twitch App-Token fehlt")
        query = urllib.parse.urlencode([("user_login", login) for login in logins])
        live_data = _twitch_http_json(
            f"https://api.twitch.tv/helix/streams?{query}",
            headers={"Client-Id": client_id, "Authorization": f"Bearer {app_token}"},
        )
        streams = live_data.get("data", [])
        live_rows = []
        if isinstance(streams, list):
            for stream in streams:
                if not isinstance(stream, dict):
                    continue
                login = str(stream.get("user_login") or "").lower()
                account = accounts.get(login)
                if account:
                    live_rows.append({**account, **stream})
        live_rows.sort(key=lambda row: (int(row.get("viewer_count") or 0), int(row.get("last_seen") or 0)), reverse=True)
    except Exception:
        st.info("Die Live-Anzeige ist gerade nicht verfügbar. Bitte lade die Startseite später erneut.")
        return

    if not live_rows:
        st.info("Aktuell ist kein StreamDex-Nutzer mit verbundenem Tool auf Twitch live.")
        return

    st.markdown(
        """
        <style>
        .sd-live-toolbar{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:8px 0 17px;padding:12px 15px;border-radius:12px;border:1px solid rgba(100,116,139,.24);background:linear-gradient(100deg,rgba(20,28,52,.9),rgba(13,24,43,.8))}
        .sd-live-count{font-size:.8rem;font-weight:700;color:#dbeafe}
        .sd-live-refresh{font-size:.72rem;color:#94a3b8}
        .sd-live-badge{display:inline-flex;align-items:center;gap:7px;border:1px solid rgba(248,113,113,.3);border-radius:99px;padding:5px 9px;background:rgba(127,29,29,.24);font-size:.68rem;font-weight:850;letter-spacing:.07em;color:#fecaca}
        .sd-live-dot{width:7px;height:7px;display:inline-block;border-radius:50%;background:#f87171;box-shadow:0 0 10px rgba(248,113,113,.8)}
        .sd-live-title{font-size:.91rem;font-weight:750;line-height:1.45;color:#f1f5f9;margin:8px 0 5px}
        .sd-live-game{font-size:.73rem;color:#c4b5fd;margin-bottom:7px}
        .sd-live-card-copy{font-size:.78rem;color:#aab7d0;line-height:1.5;min-height:36px}
        [class*="st-key-sd-live-card-"] [data-testid="stVerticalBlockBorderWrapper"]{border:1px solid rgba(100,116,139,.27)!important;border-radius:18px!important;background:linear-gradient(160deg,rgba(16,24,46,.98),rgba(10,17,32,.98))!important;box-shadow:0 12px 28px rgba(0,0,0,.18)!important;padding:10px!important;transition:transform .18s ease,border-color .18s ease,box-shadow .18s ease}
        [class*="st-key-sd-live-card-"] [data-testid="stVerticalBlockBorderWrapper"]:hover{border-color:rgba(168,85,247,.55)!important;box-shadow:0 18px 38px rgba(0,0,0,.27),0 0 20px rgba(139,92,246,.09)!important;transform:translateY(-2px)}
        [class*="st-key-sd-live-card-"] [data-testid="stImage"] img{display:block;width:100%;aspect-ratio:16/9;object-fit:cover;border-radius:11px;border:1px solid rgba(148,163,184,.16)}
        [class*="st-key-sd-live-card-"] [data-testid="stMetric"]{background:rgba(30,41,59,.38);border:1px solid rgba(148,163,184,.1);border-radius:10px;padding:8px 10px}
        [class*="st-key-sd-live-card-"] [data-testid="stMetricLabel"]{font-size:.68rem}
        [class*="st-key-sd-live-card-"] [data-testid="stMetricValue"]{font-size:1.12rem}
        @media(max-width:760px){.sd-live-toolbar{align-items:flex-start;flex-direction:column;gap:5px}}
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="sd-live-toolbar"><span class="sd-live-count">🔴 {len(live_rows)} '
        f'Live-Streamer auf StreamDex</span><span class="sd-live-refresh">↻ Aktualisiert sich ungefähr jede Minute</span></div>',
        unsafe_allow_html=True,
    )
    for start in range(0, min(len(live_rows), 12), 3):
        cols = st.columns(3, gap="medium")
        for col, stream in zip(cols, live_rows[start:start + 3]):
            login = str(stream.get("user_login") or stream["login"])
            stream_id = str(stream.get("id") or stream["tid"])
            safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", stream_id)[:80]
            name = str(stream.get("user_name") or stream["name"])
            game = str(stream.get("game_name") or "Twitch-Stream")
            title = str(stream.get("title") or "").strip()
            thumb = str(stream.get("thumbnail_url") or "")
            thumb = thumb.replace("{width}", "640").replace("{height}", "360")
            if not thumb.startswith("https://static-cdn.jtvnw.net/"):
                thumb = ""
            with col:
                with st.container(key=f"sd-live-card-{safe_id}", border=True):
                    if thumb:
                        st.image(thumb, use_container_width=True)
                    st.markdown('<span class="sd-live-badge"><span class="sd-live-dot"></span> LIVE AUF TWITCH</span>', unsafe_allow_html=True)
                    st.markdown(f'<div class="sd-live-title">{html.escape(name)}</div>', unsafe_allow_html=True)
                    st.markdown(f'<div class="sd-live-game">🎮 {html.escape(game)}</div>', unsafe_allow_html=True)
                    st.markdown(
                        f'<div class="sd-live-card-copy">{html.escape(title[:180]) if title else "Live-Stream auf Twitch"}</div>',
                        unsafe_allow_html=True,
                    )
                    viewers_col, tool_col = st.columns(2, gap="small")
                    viewers_col.metric("Zuschauer", int(stream.get("viewer_count") or 0))
                    tool_col.markdown(
                        '<div style="padding:8px 0;font-size:.69rem;color:#86efac;font-weight:750">● STREAMDEX AKTIV</div>',
                        unsafe_allow_html=True,
                    )
                    st.link_button(
                        "▶️ Jetzt ansehen",
                        f"https://www.twitch.tv/{urllib.parse.quote(login)}",
                        key=f"homepage_live_stream_{safe_id}",
                        use_container_width=True,
                    )
    if len(live_rows) > 12:
        st.caption(f"Es werden 12 von {len(live_rows)} aktiven Streams angezeigt.");


def _render_landing():
    """Öffentliche StreamDex-Startseite im Referenzdesign mit funktionalem Twitch-Login."""
    landing_css = """<style>
    /* Vollbreite öffentliche Landingpage: der Browser-Viewport gehört der Seite, nicht dem Streamlit-Rahmen. */
    header[data-testid="stHeader"],#MainMenu,footer[data-testid="stFooter"]{display:none!important}
    .block-container,[data-testid="stMainBlockContainer"]{width:100%!important;max-width:none!important;margin:0!important;
      padding:.55rem 2.75vw 0!important}
    div[data-testid="stAppViewContainer"]>.main{background:transparent!important}
    div[data-testid="stMainBlockContainer"]>div{max-width:none!important}
    .stApp{background-color:#050817!important;background-image:
      radial-gradient(ellipse at 60% 8%,rgba(61,30,133,.16),transparent 32%),
      radial-gradient(ellipse at 100% 78%,rgba(13,93,132,.09),transparent 35%),
      linear-gradient(130deg,#050817,#080b1b 55%,#050817)!important}
    .sd-public-nav{display:flex;align-items:center;gap:28px;min-height:51px;padding:0 0 12px;margin:0 0 0;border-bottom:1px solid rgba(148,163,184,.17);color:#dce4ff;width:100%}
    .sd-public-brand{display:flex;align-items:center;gap:10px;margin-right:40px;font-size:1.05rem;font-weight:800;white-space:nowrap}
    .sd-public-mark{display:grid;place-items:center;width:31px;height:31px;border-radius:9px;background:linear-gradient(135deg,#bb4dff,#4f46e5);color:#fff;font-size:19px;font-weight:900;box-shadow:0 0 18px #7c3aed55}
    .sd-public-brand span:last-child{background:linear-gradient(90deg,#fff,#c4b5fd);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
    .sd-public-brand em{font-style:normal;color:#a78bfa;-webkit-text-fill-color:#a78bfa}
    .sd-public-links{display:flex;align-items:center;gap:clamp(14px,3vw,40px);font-size:.75rem}
    .sd-public-links a,.sd-public-sun{color:#bac5e5;text-decoration:none}
    .sd-public-links a:hover{color:#fff}
    .sd-public-sun{margin-left:auto;font-size:1.2rem}
    .sd-public-hero{display:grid;grid-template-columns:minmax(0,.9fr) minmax(0,1.1fr);gap:5px;align-items:center;min-height:414px;position:relative;margin:0;padding:12px 0 15px;overflow:hidden;width:100%}
    .sd-public-copy{position:relative;z-index:2;padding:18px 5px 20px 0;min-width:0}
    .sd-public-pill{display:inline-flex;border:1px solid rgba(139,92,246,.5);border-radius:99px;background:rgba(76,29,149,.16);padding:6px 12px;color:#c4a5ff;font-size:.62rem;letter-spacing:.09em;font-weight:800}
    .sd-public-title{font-size:clamp(2rem,3.15vw,3.08rem)!important;line-height:1.07!important;letter-spacing:-.055em!important;margin:15px 0 15px!important;color:#f4f6ff!important;font-weight:800!important;max-width:680px!important}
    .sd-public-title span{color:#b45cff;background:linear-gradient(90deg,#c15bff,#8b5cf6);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
    .sd-public-description{color:#c0c9e2;font-size:.82rem;line-height:1.85;max-width:520px}
    .sd-public-cta{display:flex;align-items:center;gap:11px;flex-wrap:wrap;margin-top:19px}
    .sd-public-cta a{display:inline-flex;align-items:center;gap:9px;padding:12px 16px;text-decoration:none;border-radius:9px;font-size:.72rem;font-weight:800}
    .sd-public-cta .main{color:#fff;background:linear-gradient(105deg,#a044f2,#4936ee);border:1px solid #8f5aff;box-shadow:0 7px 22px #6934e933}
    .sd-public-cta .alt{color:#dce4ff;background:rgba(8,13,30,.55);border:1px solid #303b60}
    .sd-public-trust{display:flex;gap:13px 18px;flex-wrap:wrap;margin-top:27px;color:#aeb9db;font-size:.61rem}
    .sd-public-trust span::first-letter{color:#b78aff}
    .sd-public-art{height:378px;min-width:0;width:100%;position:relative;isolation:isolate;overflow:hidden;background:radial-gradient(ellipse at 53% 50%,rgba(87,42,196,.55),transparent 57%)}
    .sd-public-art:before{content:"";position:absolute;inset:9% 6% 12%;border:1px solid rgba(99,102,241,.28);border-radius:50%;transform:rotate(-18deg);box-shadow:0 0 60px rgba(90,45,220,.25)}
    .sd-public-art:after{content:"";position:absolute;inset:23% -4% 27%;border:1px solid rgba(34,211,238,.42);border-radius:50%;transform:rotate(22deg)}
    .sd-public-orbit{position:absolute;inset:14% 11%;border:1px solid rgba(139,92,246,.35);border-radius:50%;transform:rotate(35deg)}
    .sd-public-neon{position:absolute;right:6%;top:3%;padding:10px 12px;border:1px solid #7c3aed;border-radius:6px;color:#d9b4ff;background:#210d42;font-size:.65rem;letter-spacing:.13em;box-shadow:0 0 24px #a855f766;transform:rotate(-8deg)}
    .sd-public-screen{position:absolute;z-index:2;left:8%;top:17%;width:85%;height:69%;border:1px solid #8b5cf6;border-radius:12px;background:linear-gradient(130deg,rgba(8,15,34,.98),rgba(19,17,53,.95));box-shadow:0 0 0 4px #8b5cf61a,0 0 45px #6d28d966;transform:perspective(900px) rotateY(-8deg) rotateX(2deg);overflow:hidden}
    .sd-public-screenbar{display:flex;align-items:center;gap:7px;height:30px;padding:0 10px;border-bottom:1px solid #30305e;background:#151a3a;color:#bcbfea;font-size:.52rem}
    .sd-public-screenlogo{display:grid;place-items:center;width:16px;height:16px;border-radius:5px;background:linear-gradient(135deg,#c05aff,#4f46e5);color:white;font-weight:900}
    .sd-public-windowdots{margin-left:auto;color:#817bb5}
    .sd-public-screenbody{display:grid;grid-template-columns:27px 1fr;height:calc(100% - 30px)}
    .sd-public-screenside{padding:12px 7px;border-right:1px solid #28294d;color:#bb8cff;line-height:2.4;font-size:.64rem}
    .sd-public-screenmain{padding:12px 10px}
    .sd-public-screenmain small{display:block;color:#8e9aba;font-size:.47rem;letter-spacing:.12em}
    .sd-public-screenmain strong{display:block;margin:4px 0 10px;font-size:.92rem;color:#f2f4ff}
    .sd-public-ministats{display:grid;grid-template-columns:repeat(3,1fr);gap:5px}
    .sd-public-ministats span{padding:7px 5px;border:1px solid #2c355b;border-radius:5px;background:#111b37;font-size:.46rem;color:#9ba8ca}
    .sd-public-ministats b{display:block;font-size:.75rem;color:#f2f4ff;margin-top:5px}
    .sd-public-minibars{display:flex;align-items:end;gap:5px;height:47px;margin-top:9px}
    .sd-public-minibars i{display:block;flex:1;height:55%;border-radius:3px 3px 0 0;background:linear-gradient(#bf66ff,#5145e8)}
    .sd-public-minibars i:nth-child(2){height:38%}.sd-public-minibars i:nth-child(3){height:74%}.sd-public-minibars i:nth-child(4){height:56%}.sd-public-minibars i:nth-child(5){height:95%}.sd-public-minibars i:nth-child(6){height:69%}.sd-public-minibars i:nth-child(7){height:82%}
    .sd-public-float{position:absolute;z-index:3;display:grid;place-items:center;width:38px;height:38px;border:1px solid #8b5cf6;border-radius:11px;color:#d6b4ff;background:#201044;box-shadow:0 0 22px #8b5cf655;font-size:1.1rem}
    .sd-public-f1{top:6%;left:24%}.sd-public-f2{top:36%;left:0;color:#67e8f9;border-color:#22d3ee}.sd-public-f3{bottom:5%;right:12%}.sd-public-f4{top:9%;right:21%;color:#67e8f9;border-color:#22d3ee}
    div[data-testid="stHorizontalBlock"]:has(.st-key-sd_login_card){
      display:grid!important;
      grid-template-columns:minmax(0,3.8fr) minmax(294px,1.08fr)!important;
      gap:22px!important;align-items:start!important;width:100%!important;margin:0!important
    }
    div[data-testid="stHorizontalBlock"]:has(.st-key-sd_login_card)>div{width:100%!important;min-width:0!important;flex:none!important;padding:0!important}
    div[data-testid="stHorizontalBlock"]:has(.st-key-sd_login_card)>div>div{width:100%!important}
    @media(max-width:1050px){div[data-testid="stHorizontalBlock"]:has(.st-key-sd_login_card){grid-template-columns:minmax(0,1fr)!important;gap:12px!important}}\n    .st-key-sd_login_card{margin:0 0 18px!important;padding:18px 17px 14px!important;border:1px solid rgba(139,92,246,.46)!important;border-radius:13px!important;background:linear-gradient(150deg,rgba(14,17,42,.97),rgba(8,12,27,.98))!important;box-shadow:0 10px 35px rgba(0,0,0,.28)!important}
    .st-key-sd_login_card [data-testid="stMarkdownContainer"] h2{font-size:1.18rem!important;margin:0 0 6px!important}
    .st-key-sd_login_card [data-testid="stMarkdownContainer"] p{color:#aeb9db;font-size:.72rem;line-height:1.6}
    .sd-public-login-brand{display:flex;justify-content:center;align-items:center;gap:8px;font-weight:800;font-size:.98rem;margin:0 0 18px;background:linear-gradient(90deg,#fff,#c4b5fd);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
    .sd-public-login-note{color:#8e9aba;font-size:.62rem;line-height:1.6;text-align:center;margin:9px 0}
    .sd-public-separator{display:flex;align-items:center;gap:10px;color:#8792b2;font-size:.62rem;margin:12px 0}
    .sd-public-separator:before,.sd-public-separator:after{content:"";height:1px;background:#273152;flex:1}
    .sd-public-start{padding:20px 0 22px;margin:3px 0 0;border-bottom:1px solid rgba(148,163,184,.17)}
    .sd-public-start-head{display:flex;align-items:flex-end;justify-content:space-between;gap:14px;margin-bottom:13px}
    .sd-public-start h2{font-size:1.22rem!important;color:#f1f5ff;margin:0 0 5px!important;letter-spacing:-.035em!important}
    .sd-public-start-intro{color:#a7b4d5;font-size:.7rem;line-height:1.7;margin:0}
    .sd-public-start-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
    .sd-public-start-card{display:flex;align-items:flex-start;gap:11px;padding:14px;border:1px solid rgba(48,61,103,.8);border-radius:12px;background:linear-gradient(145deg,rgba(13,19,40,.88),rgba(9,14,29,.94));min-width:0}
    .sd-public-start-num{display:grid;place-items:center;flex:0 0 32px;width:32px;height:32px;border-radius:10px;background:rgba(139,92,246,.17);border:1px solid rgba(139,92,246,.4);color:#d8b4fe;font-weight:800}
    .sd-public-start-card b{display:block;font-size:.73rem;color:#f1f5ff;margin:1px 0 5px}
    .sd-public-start-card p{font-size:.64rem;color:#a5b2d2;line-height:1.6;margin:0}
    .sd-public-start-actions{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:13px}
    .sd-public-start-actions a{display:inline-flex;padding:9px 12px;border:1px solid rgba(139,92,246,.45);border-radius:9px;background:rgba(76,29,149,.18);color:#d8b4fe;text-decoration:none;font-size:.68rem;font-weight:750}
    .sd-public-start-actions a:hover{border-color:#a78bfa;color:#fff}
    @media(max-width:760px){.sd-public-start-grid{grid-template-columns:1fr}.sd-public-start-card{padding:12px}.sd-public-start-head{align-items:flex-start;flex-direction:column}}
    .sd-public-benefits{border-top:1px solid rgba(148,163,184,.17);border-bottom:1px solid rgba(148,163,184,.17);padding:19px 0 21px;display:grid;grid-template-columns:minmax(230px,1.12fr) repeat(4,minmax(0,1fr));gap:12px;align-items:stretch;width:100%}
    .sd-public-benefit-intro{padding:8px 10px 8px 0}
    .sd-public-benefit-intro h2{font-size:1.32rem!important;letter-spacing:-.04em!important;margin:0 0 7px!important;color:#eff2ff}
    .sd-public-benefit-intro p{font-size:.7rem;line-height:1.7;color:#a6b1d0;margin:0}
    .sd-public-benefit{border:1px solid rgba(48,61,103,.8);border-radius:11px;background:linear-gradient(145deg,rgba(13,19,40,.88),rgba(9,14,29,.94));padding:13px 13px;min-height:109px}
    .sd-public-benefit-icon{font-size:1.55rem;color:#b56cff;margin-bottom:10px;text-shadow:0 0 15px #8b5cf655}
    .sd-public-benefit b{display:block;color:#edf0ff;font-size:.68rem;margin-bottom:8px}
    .sd-public-benefit p{font-size:.59rem;line-height:1.6;color:#9aa6c8;margin:0}
    .sd-public-tools{padding:20px 5px 25px;width:100%}
    .sd-public-toolshead{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:15px}
    .sd-public-toolshead h2{font-size:1.3rem!important;margin:0 0 5px!important;letter-spacing:-.04em!important;color:#edf0ff}
    .sd-public-toolshead p{margin:0;font-size:.72rem;color:#a6b1d0}
    .sd-public-count{font-size:.62rem;color:#baa3ff;background:#24154b;border:1px solid #3e2876;padding:5px 8px;border-radius:5px;margin-left:8px;white-space:nowrap}
    .sd-public-all{color:#bda1ff;text-decoration:none;font-size:.65rem;white-space:nowrap}
    .sd-public-toolgrid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:9px;width:100%}
    .sd-public-tool{display:flex;align-items:flex-start;gap:10px;min-height:82px;padding:12px 10px;border:1px solid #222e52;border-radius:10px;background:linear-gradient(145deg,rgba(12,18,38,.94),rgba(8,13,28,.98));color:#edf1ff;text-decoration:none;transition:transform .16s,border-color .16s}
    .sd-public-tool:hover{border-color:#7c5ad5;transform:translateY(-2px);color:#fff}
    .sd-public-tool-icon{flex:0 0 35px;width:35px;height:35px;display:grid;place-items:center;border-radius:50%;font-size:1.12rem;color:#c99aff;background:radial-gradient(circle,#49217e,#1d123d 72%);box-shadow:0 0 17px #7839b82a}
    .sd-public-tool-icon.cyan{color:#51dcf5;background:radial-gradient(circle,#124b69,#0b1d35 72%)}
    .sd-public-tool b{display:block;font-size:.66rem;margin:3px 0 5px}
    .sd-public-tool small{display:block;color:#a0accd;font-size:.57rem;line-height:1.5}
    .sd-public-footer{display:flex;align-items:center;justify-content:space-between;gap:18px;margin:0 -2.75vw;width:calc(100% + 5.5vw);padding:17px 2.75vw;background:radial-gradient(ellipse at left,#35126f 0,transparent 48%),linear-gradient(95deg,#10082a,#080e23 60%,#111037);border-top:1px solid #30205f}
    .sd-public-footer-brand{display:flex;align-items:center;gap:9px;color:#f0efff;font-weight:800;font-size:.82rem}
    .sd-public-footer-brand small{display:block;font-size:.58rem;color:#a6b1d0;font-weight:400;margin-top:3px}
    .sd-public-footer-mid{display:flex;gap:17px;flex-wrap:wrap;color:#a6b1d0;font-size:.58rem}
    .sd-public-footer-cta{color:#fff!important;background:linear-gradient(100deg,#8b3df0,#5038ed);border:1px solid #865bfa;border-radius:8px;padding:10px 13px;text-decoration:none;font-size:.65rem;font-weight:800;white-space:nowrap}
    @media(max-width:1350px){
      .sd-public-hero{grid-template-columns:minmax(0,.95fr) minmax(0,1.05fr);min-height:385px}
      .sd-public-title{font-size:clamp(1.9rem,3vw,2.5rem)!important}
      .sd-public-art{height:340px}
      .sd-public-benefits{grid-template-columns:repeat(4,minmax(0,1fr))}
      .sd-public-benefit-intro{grid-column:1/-1}
      .sd-public-toolgrid{grid-template-columns:repeat(4,minmax(0,1fr))}
    }
    @media(max-width:1050px){
      .sd-public-hero{grid-template-columns:minmax(0,1fr);padding-bottom:10px}
      .sd-public-art{height:330px;margin-top:-4px}
      .sd-public-copy{padding:20px 0}
      .sd-public-benefits{grid-template-columns:repeat(2,minmax(0,1fr))}
      .sd-public-benefit-intro{grid-column:1/-1}
      .sd-public-toolgrid{grid-template-columns:repeat(3,minmax(0,1fr))}
    }
    @media(max-width:760px){
      .block-container,[data-testid="stMainBlockContainer"]{padding:.4rem 14px 0!important}
      .sd-public-nav{gap:12px;flex-wrap:wrap}
      .sd-public-brand{margin-right:auto}
      .sd-public-links{order:3;width:100%;justify-content:space-between;gap:10px;font-size:.68rem}
      .sd-public-hero{min-height:0}
      .sd-public-title{font-size:2.1rem!important}
      .sd-public-art{height:280px}
      .sd-public-benefits{grid-template-columns:repeat(2,minmax(0,1fr))}
      .sd-public-benefit-intro{grid-column:1/-1}
      .sd-public-toolgrid{grid-template-columns:repeat(2,minmax(0,1fr))}
      .sd-public-footer{align-items:flex-start;flex-direction:column}
      .sd-public-footer-mid{display:none}
      .sd-public-toolshead{align-items:flex-start}
      .st-key-sd_login_card{padding:17px!important}
    }
    @media(max-width:430px){
      .sd-public-toolgrid{grid-template-columns:1fr}
      .sd-public-benefits{grid-template-columns:1fr 1fr}
      .sd-public-art{height:220px}
      .sd-public-title{font-size:1.9rem!important}
      .sd-public-cta a{padding:11px 12px}
    }
    </style>"""
    st.markdown(landing_css, unsafe_allow_html=True)

    st.markdown(
        '<div class="sd-public-nav" id="top">'
        '<div class="sd-public-brand"><span class="sd-public-mark">S</span><span>StreamDex <em>OS</em></span></div>'
        '<nav class="sd-public-links"><a href="#top">Home</a><a href="#features">Features</a><a href="#tools">Tools</a>'
        '<a href="#tools">Preise</a><a href="#faq">FAQ</a></nav><a class="sd-public-sun" href="#top" title="StreamDex OS">☼</a></div>',
        unsafe_allow_html=True,
    )

    hero_left, login_right = st.columns([2.75, 1.0], gap="medium")
    with hero_left:
        st.markdown(
            '<div class="sd-public-hero">'
            '<div class="sd-public-copy">'
            '<span class="sd-public-pill">DEIN STREAMING-OS</span>'
            '<h1 class="sd-public-title">Alles, was du für deinen<br><span>Stream</span> brauchst – an einem Ort.</h1>'
            '<p class="sd-public-description">StreamDex OS ist deine zentrale Plattform für alle Streaming-Tools. Plane, manage, automatisiere und begeistere deine Community – einfach, flexibel und komplett auf dich zugeschnitten.</p>'
            '<div class="sd-public-cta"><a class="main" href="#sd-login-anchor">♧&nbsp; Jetzt kostenlos starten&nbsp; →</a>'
            '<a class="alt" href="#features">▷&nbsp; Mehr erfahren</a></div>'
            '<div class="sd-public-trust"><span>▦ Alle Tools in einer Plattform</span><span>♙ Ein Login. Alles verfügbar.</span><span>⟳ Regelmäßige Updates</span><span>♡ Für Streamer. Von Streamern.</span></div>'
            '</div>'
            '<div class="sd-public-art"><div class="sd-public-orbit"></div><div class="sd-public-neon">GOOD<br>VIBES</div>'
            '<div class="sd-public-float sd-public-f1">▦</div><div class="sd-public-float sd-public-f2">♧</div>'
            '<div class="sd-public-float sd-public-f3">◈</div><div class="sd-public-float sd-public-f4">🎮</div>'
            '<div class="sd-public-screen"><div class="sd-public-screenbar"><span class="sd-public-screenlogo">S</span> StreamDex OS <span class="sd-public-windowdots">•••</span></div>'
            '<div class="sd-public-screenbody"><div class="sd-public-screenside">⌂<br>▦<br>♙<br>⚙</div>'
            '<div class="sd-public-screenmain"><small>DEIN WORKSPACE</small><strong>Willkommen zurück!</strong>'
            '<div class="sd-public-ministats"><span>Follower<b>12.4K</b></span><span>Zuschauer<b>284</b></span><span>Onlinezeit<b>152h</b></span></div>'
            '<div class="sd-public-minibars"><i></i><i></i><i></i><i></i><i></i><i></i><i></i></div></div></div></div></div>'
            '</div>',
            unsafe_allow_html=True,
        )

    with login_right:
        with st.container(key="sd_login_card"):
            st.markdown(
                '<div class="sd-public-login-brand"><span class="sd-public-mark">S</span> StreamDex OS</div>'
                '<h2>Willkommen zurück!</h2>'
                '<p>Melde dich an, um auf deine Tools zuzugreifen.</p>'
                '<div id="sd-login-anchor"></div>',
                unsafe_allow_html=True,
            )
            _render_twitch_login()
            st.markdown(
                '<div class="sd-public-separator">sicher anmelden</div>'
                '<div class="sd-public-login-note">Ein geschützter Login über Twitch. Dein StreamDex-Dashboard wartet auf dich.</div>'
                '<div class="sd-public-login-note" id="faq">Du hast Fragen? Schau in die Anleitungen oder besuche unseren Support.</div>',
                unsafe_allow_html=True,
            )

    st.markdown(
        '<section class="sd-public-start" aria-label="StreamDex Schnellstart">'
        '<div class="sd-public-start-head"><div><h2>Dein erster Erfolg in drei Schritten</h2>'
        '<p class="sd-public-start-intro">Starte klein: anmelden, eine Idee festhalten und den nächsten Stream planen.</p></div></div>'
        '<div class="sd-public-start-grid">'
        '<div class="sd-public-start-card"><span class="sd-public-start-num">1</span><div><b>Mit Twitch anmelden</b><p>Ein Login verbindet dein Creator-Dashboard mit deinem Konto.</p></div></div>'
        '<div class="sd-public-start-card"><span class="sd-public-start-num">2</span><div><b>Eine Idee speichern</b><p>Halte den ersten Content-Einfall oder Community-Wunsch fest.</p></div></div>'
        '<div class="sd-public-start-card"><span class="sd-public-start-num">3</span><div><b>Deinen Stream planen</b><p>Lege einen Termin an und behalte deinen nächsten Stream im Blick.</p></div></div>'
        '</div><div class="sd-public-start-actions">'
        '<a href="#sd-login-anchor">Jetzt mit Twitch starten →</a><a href="/?tour=1">Geführten Rundgang ansehen →</a>'
        '</div></section>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<section class="sd-public-benefits" id="features">'
        '<div class="sd-public-benefit-intro"><h2>Mehr als nur ein Tool</h2>'
        '<p>StreamDex OS bietet dir eine wachsende Sammlung an Tools, die dir helfen, deinen Stream zu optimieren, deine Community zu stärken und deine Ideen umzusetzen.</p></div>'
        '<div class="sd-public-benefit"><div class="sd-public-benefit-icon">ϟ</div><b>Zeitsparend</b><p>Automatisiere wiederkehrende Aufgaben und konzentriere dich auf das Wesentliche.</p></div>'
        '<div class="sd-public-benefit"><div class="sd-public-benefit-icon">♧</div><b>Community</b><p>Mehr Interaktion, mehr Engagement, mehr Spaß.</p></div>'
        '<div class="sd-public-benefit"><div class="sd-public-benefit-icon">⚙</div><b>Flexibel</b><p>Passe alles an deine Bedürfnisse an – von Commands bis zu Events.</p></div>'
        '<div class="sd-public-benefit"><div class="sd-public-benefit-icon">⬡</div><b>Sicher</b><p>Deine Daten bleiben in deinen besten Händen.</p></div>'
        '</section>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<section class="sd-public-tools" id="tools"><div class="sd-public-toolshead"><div><h2>'
        'Unsere Tools – Dein Vorteil <span class="sd-public-count">30+ Tools</span></h2>'
        '<p>Von der Stream-Planung bis zur Community-Verwaltung – alles, was du brauchst.</p></div>'
        '<a class="sd-public-all" href="#tools">Alle Tools anzeigen →</a></div>'
        '<div class="sd-public-toolgrid">'
        '<a class="sd-public-tool" href="/?dashboard=1"><span class="sd-public-tool-icon">🎮</span><span><b>Multi Tool</b><small>Chat Games, Kanalpunkte, Commands, Automationen und mehr.</small></span></a>'
        '<a class="sd-public-tool" href="/?planner=1"><span class="sd-public-tool-icon">▣</span><span><b>Planner</b><small>Stream-Planung, Kalender und Erinnerungen.</small></span></a>'
        '<a class="sd-public-tool" href="/?events=1"><span class="sd-public-tool-icon">♜</span><span><b>Events</b><small>Community-Events, Turniere und Specials.</small></span></a>'
        '<a class="sd-public-tool" href="/?radar=1"><span class="sd-public-tool-icon cyan">◉</span><span><b>Radar</b><small>Live-Status, Statistiken und mehrere Streamer im Blick.</small></span></a>'
        '<a class="sd-public-tool" href="/?dashboard=1"><span class="sd-public-tool-icon">⚑</span><span><b>Promo</b><small>Ankündigungen, Grafikvorlagen und Social Media.</small></span></a>'
        '<a class="sd-public-tool" href="/?dashboard=1"><span class="sd-public-tool-icon cyan">◉</span><span><b>Lurk Tool</b><small>Browser öffnet sich automatisch, wenn ein Stream live geht.</small></span></a>'
        '<a class="sd-public-tool" href="/?feedback=1"><span class="sd-public-tool-icon cyan">▤</span><span><b>Feedback</b><small>Umfragen, Vorschläge und Community-Feedback.</small></span></a>'
        '<a class="sd-public-tool" href="/?ideas=1"><span class="sd-public-tool-icon">💡</span><span><b>StreamDex Ideas</b><small>Ideen sammeln, priorisieren und umsetzen.</small></span></a>'
        '<a class="sd-public-tool" href="/?bracket=1"><span class="sd-public-tool-icon">🏆</span><span><b>StreamDex Bracket</b><small>Turnierbäume und Match-Ergebnisse.</small></span></a>'
        '<a class="sd-public-tool" href="/?wheel=1"><span class="sd-public-tool-icon cyan">🎡</span><span><b>StreamDex Wheel</b><small>Glücksrad für Entscheidungen und Giveaways.</small></span></a>'
        '<a class="sd-public-tool" href="/?wishlist=1"><span class="sd-public-tool-icon">🎁</span><span><b>StreamDex Wishlist</b><small>Community-Wünsche und Abstimmungen.</small></span></a>'
        '<a class="sd-public-tool" href="/?quiz=1"><span class="sd-public-tool-icon cyan">🧠</span><span><b>StreamDex Quiz</b><small>Quizräume erstellen, teilen und spielen.</small></span></a>'
        '<a class="sd-public-tool" href="/?clips=1"><span class="sd-public-tool-icon">🎬</span><span><b>StreamDex Clips</b><small>Highlights sammeln, taggen und wiederfinden.</small></span></a>'
        '<a class="sd-public-tool" href="/?goals=1"><span class="sd-public-tool-icon cyan">🎯</span><span><b>StreamDex Goals</b><small>Ziele setzen und Fortschritt verfolgen.</small></span></a>'
        '<a class="sd-public-tool" href="/?modlog=1"><span class="sd-public-tool-icon">🛡️</span><span><b>StreamDex ModLog</b><small>Moderationsaktionen sauber protokollieren.</small></span></a>'
        '<a class="sd-public-tool" href="/?modteam=1"><span class="sd-public-tool-icon cyan">👥</span><span><b>StreamDex ModTeam</b><small>Rollen, Zuständigkeiten und Aufgaben planen.</small></span></a>'
        '<a class="sd-public-tool" href="/?profile=1"><span class="sd-public-tool-icon cyan">♙</span><span><b>Profile</b><small>Dein öffentliches Creator-Profil mit allen Infos.</small></span></a>'
        '<a class="sd-public-tool" href="/?dashboard=1"><span class="sd-public-tool-icon cyan">⚙</span><span><b>Automation</b><small>Automationen für Chat, Events, Commands und mehr.</small></span></a>'
        '<a class="sd-public-tool" href="/?dashboard=1"><span class="sd-public-tool-icon">▱</span><span><b>Overlay Editor</b><small>Gestalte deine Overlays einfach und professionell.</small></span></a>'
        '</div></section>',
        unsafe_allow_html=True,
    )
    _render_public_live_streamers()

    st.markdown(
        '<footer class="sd-public-footer"><div class="sd-public-footer-brand"><span class="sd-public-mark">S</span>'
        '<span>StreamDex OS<small>Dein Streaming. Unsere Mission.</small></span></div>'
        '<div class="sd-public-footer-mid"><span>⟳ Kontinuierliche Weiterentwicklung</span><span>▣ Twitch & mehr Integrationen</span><span>♡ Für alle Streamer</span></div>'
        '<a class="sd-public-footer-cta" href="#sd-login-anchor">Jetzt starten →</a></footer>',
        unsafe_allow_html=True,
    )


def _render_member_downloads_and_beta(authed_tid, twitch_username, beta_info=None):
    """Downloads, Beta-Bewerbung und Status sind ausschließlich im authentifizierten Dashboard sichtbar."""
    st.markdown(
        '<div class="sd-section-heading"><div class="sd-section-kicker">MITGLIEDERBEREICH</div>'
        '<h2>Downloads & Beta</h2>'
        '<p>Hier findest du die StreamDex-Version, deine Beta-Bewerbung und den Status deiner Bewerbung.</p></div>',
        unsafe_allow_html=True,
    )
    try:
        cfg = download_settings()
        t_dl, t_apply, t_status = st.tabs(["⬇️ Downloads", "🧪 Für Beta bewerben", "🔎 Beta-Status"])
        with t_dl:
            st.markdown("#### StreamDex herunterladen")
            st.caption("Die Download-Links sind nur nach der Anmeldung verfügbar.")
            render_public_downloads(cfg)
            if beta_info:
                st.divider()
                st.markdown("#### Deine Beta-Version")
                render_member_downloads(cfg)
            else:
                st.caption("Der Beta-Download erscheint hier, sobald du für die Beta freigeschaltet bist.")
        account_name = str(
            (st.session_state.get("twitch_profile", {}) or {}).get("login")
            or twitch_username
            or ""
        )
        with t_apply:
            _apply_form(cfg, default_name=account_name)
        with t_status:
            render_logged_in_beta_status(authed_tid, account_name, beta_info, cfg)
    except Exception as e:
        st.error(f"Downloads und Beta-Informationen sind gerade nicht erreichbar. ({type(e).__name__})")


STREAMER_DASHBOARD_CSS = """<style>
/* Scoped to the streamer dashboard. Admin and data/auth logic stay untouched. */
.sd-hero{position:relative;isolation:isolate;overflow:hidden;margin:0 0 18px;padding:clamp(22px,3.4vw,36px);border:1px solid rgba(168,85,247,.3);border-radius:24px;background:linear-gradient(115deg,rgba(15,23,42,.98) 0%,rgba(35,25,71,.94) 52%,rgba(8,47,73,.9) 100%);box-shadow:0 20px 55px rgba(0,0,0,.26),inset 0 1px 0 rgba(255,255,255,.06)}
.sd-hero:before{content:"";position:absolute;z-index:-1;top:-155px;right:-65px;width:390px;height:390px;border-radius:50%;background:radial-gradient(circle,rgba(6,182,212,.19),rgba(168,85,247,.12) 42%,transparent 70%);pointer-events:none}
.sd-hero:after{content:"";position:absolute;z-index:-1;right:14%;bottom:-190px;width:330px;height:260px;border-radius:50%;background:radial-gradient(circle,rgba(168,85,247,.18),transparent 70%);pointer-events:none}
.sd-hero-kicker{display:flex;align-items:center;gap:9px;color:#c4b5fd;font-family:'JetBrains Mono',monospace;font-size:.69rem;font-weight:700;letter-spacing:.12em;text-transform:uppercase}
.sd-hero-dot{width:7px;height:7px;flex:0 0 7px;border-radius:50%;background:#22d3ee;box-shadow:0 0 12px rgba(34,211,238,.9)}
.sd-hero-slash{color:#64748b}
.sd-hero-title{margin:15px 0 8px!important;font-size:clamp(1.85rem,4vw,2.8rem)!important;line-height:1.12!important;letter-spacing:-.055em!important;color:#fff}
.sd-hero-description{max-width:680px;margin:0!important;font-size:clamp(.94rem,1.5vw,1.08rem);line-height:1.7;color:#cbd5e1}
.sd-hero-tags{display:flex;flex-wrap:wrap;gap:8px;margin-top:22px}
.sd-hero-tags span{display:inline-flex;align-items:center;gap:6px;padding:7px 11px;border:1px solid rgba(255,255,255,.1);border-radius:99px;background:rgba(15,23,42,.48);color:#e2e8f0;font-size:.75rem;font-weight:700;backdrop-filter:blur(8px)}
.sd-section-heading{margin:4px 0 18px}
.sd-section-kicker{margin-bottom:5px;color:#a78bfa;font:700 .67rem 'JetBrains Mono',monospace;letter-spacing:.13em}
.sd-section-heading h2{margin:0 0 6px!important;color:#f8fafc;font-size:1.35rem!important;letter-spacing:-.035em}
.sd-section-heading p{margin:0;color:#94a3b8;max-width:760px;line-height:1.65;font-size:.9rem}
.sd-feature-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:13px;margin:18px 0 26px}
.sd-feature-card{min-width:0;padding:18px;border-radius:17px;border:1px solid rgba(148,163,184,.14);background:linear-gradient(145deg,rgba(15,23,42,.92),rgba(11,18,35,.82));box-shadow:0 10px 28px rgba(0,0,0,.16);transition:transform .18s ease,border-color .18s ease}
.sd-feature-card:hover{transform:translateY(-3px);border-color:rgba(168,85,247,.42)}
.sd-feature-icon{display:grid;place-items:center;width:42px;height:42px;margin-bottom:14px;border-radius:13px;border:1px solid rgba(168,85,247,.25);background:linear-gradient(135deg,rgba(168,85,247,.2),rgba(6,182,212,.12));font-size:1.25rem}
.sd-feature-title{margin-bottom:6px;font-weight:800;color:#f8fafc;font-size:.94rem}
.sd-feature-copy{font-size:.81rem;color:#94a3b8;line-height:1.65}
.st-key-sd_login_card{margin:0 0 22px;padding:20px 22px 14px;border:1px solid rgba(168,85,247,.24);border-radius:18px;background:linear-gradient(140deg,rgba(30,27,75,.44),rgba(15,23,42,.88));box-shadow:0 14px 35px rgba(0,0,0,.18)}
.st-key-sd_login_card [data-testid="stMarkdownContainer"] h2{margin:0 0 7px;font-size:1.2rem!important}
.st-key-sd_login_card [data-testid="stMarkdownContainer"] p{color:#cbd5e1}
.st-key-sd_profile_header{margin:0 0 18px;padding:13px 16px;border:1px solid rgba(148,163,184,.16);border-radius:18px;background:linear-gradient(120deg,rgba(15,23,42,.95),rgba(30,27,75,.7));box-shadow:0 12px 30px rgba(0,0,0,.18)}
.st-key-sd_profile_header [data-testid="stImage"] img{border-radius:16px;border:2px solid rgba(168,85,247,.45);box-shadow:0 0 20px rgba(168,85,247,.16)}
.st-key-sd_profile_header h3{margin:0 0 3px;font-size:1.25rem!important;letter-spacing:-.03em}
.st-key-sd_profile_header [data-testid="stCaptionContainer"]{font-size:.76rem}
.st-key-sd_profile_header .sd-profile-status{display:inline-flex;align-items:center;gap:6px;margin:3px 0 0;padding:4px 9px;border-radius:99px;border:1px solid rgba(148,163,184,.16);background:rgba(15,23,42,.65);font-size:.7rem;font-weight:700;color:#cbd5e1}
.st-key-sd_profile_header .sd-profile-status.online{color:#86efac;border-color:rgba(34,197,94,.25);background:rgba(34,197,94,.08)}
.st-key-sd_profile_header .sd-profile-status.offline{color:#cbd5e1}

/* Große Kachel-Navigation: drei breite Buttons pro Reihe im Streamer-Dashboard. */
.st-key-sd_main_nav [data-baseweb="tab-list"],
.st-key-sd_main_nav [role="tablist"]{
  display:grid!important;
  grid-template-columns:repeat(3,minmax(0,1fr))!important;
  gap:12px!important;
  width:100%!important;
  overflow:visible!important;
  padding:8px 0 20px!important;
  border:0!important;
  scrollbar-width:none;
}
.st-key-sd_main_nav [data-baseweb="tab-list"]::-webkit-scrollbar,
.st-key-sd_main_nav [role="tablist"]::-webkit-scrollbar{display:none!important}
.st-key-sd_main_nav button[data-baseweb="tab"],
.st-key-sd_main_nav button[role="tab"]{
  display:flex!important;
  align-items:center!important;
  justify-content:center!important;
  width:100%!important;
  min-width:0!important;
  min-height:84px!important;
  height:100%!important;
  padding:17px 14px!important;
  white-space:normal!important;
  text-align:center!important;
  border-radius:18px!important;
  border:1px solid rgba(148,163,184,.18)!important;
  background:linear-gradient(145deg,rgba(15,23,42,.96),rgba(20,29,49,.94))!important;
  color:#cbd5e1!important;
  box-shadow:0 10px 24px rgba(0,0,0,.18),inset 0 1px 0 rgba(255,255,255,.035)!important;
  transition:transform .16s ease,border-color .16s ease,box-shadow .16s ease,background .16s ease!important;
}
.st-key-sd_main_nav button[data-baseweb="tab"] p,
.st-key-sd_main_nav button[role="tab"] p,
.st-key-sd_main_nav button[role="tab"] span,
.st-key-sd_main_nav button[role="tab"] div{
  font-size:.94rem!important;
  line-height:1.35!important;
  font-weight:800!important;
  white-space:normal!important;
  text-align:center!important;
  color:inherit!important;
}
.st-key-sd_main_nav button[data-baseweb="tab"]:hover,
.st-key-sd_main_nav button[role="tab"]:hover{
  transform:translateY(-2px)!important;
  border-color:rgba(168,85,247,.65)!important;
  box-shadow:0 15px 30px rgba(0,0,0,.25),0 0 18px rgba(168,85,247,.12)!important;
}
.st-key-sd_main_nav button[role="tab"][aria-selected="true"]{
  background:linear-gradient(135deg,rgba(126,34,206,.96),rgba(8,145,178,.9))!important;
  border-color:rgba(196,181,253,.86)!important;
  color:#fff!important;
  box-shadow:0 12px 28px rgba(88,28,135,.27),inset 0 1px 0 rgba(255,255,255,.18)!important;
}
.st-key-sd_main_nav [data-baseweb="tab-highlight"],
.st-key-sd_main_nav [data-baseweb="tab-border"]{display:none!important}
@media(max-width:850px){
  .st-key-sd_main_nav [data-baseweb="tab-list"],
  .st-key-sd_main_nav [role="tablist"]{grid-template-columns:repeat(2,minmax(0,1fr))!important;gap:10px!important}
  .st-key-sd_main_nav button[data-baseweb="tab"],
  .st-key-sd_main_nav button[role="tab"]{min-height:76px!important;padding:14px 10px!important;border-radius:15px!important}
  .st-key-sd_main_nav button[role="tab"] p,
  .st-key-sd_main_nav button[role="tab"] span{font-size:.86rem!important}
}
@media(max-width:760px){
  .sd-feature-grid{grid-template-columns:1fr;gap:10px}
  .sd-feature-card{padding:15px}
  .sd-hero{border-radius:19px}
  .sd-hero-tags{margin-top:16px}
  .st-key-sd_login_card{padding:16px}
}
</style>"""


def render_streamer_dashboard(games):
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown(STREAMER_DASHBOARD_CSS, unsafe_allow_html=True)
    hero = st.empty()   # Kopfbereich wird erst gefüllt, wenn klar ist, ob jemand angemeldet ist


    # 1. Token aus URL verarbeiten (falls vorhanden)
    token_arg = st.query_params.get("token")
    if token_arg:
        valid_tid = _verify_and_consume_token(token_arg)
        if valid_tid:
            st.session_state["authenticated_tid"] = valid_tid
            st.session_state["authenticated_at"] = time.time()
            st.session_state["auth_method"] = "desktop"
            st.session_state.pop("twitch_profile", None)
            st.session_state.pop("dashboard_reauth_required", None)
            # Token aus URL entfernen für saubere Adresse
            st.query_params.clear()
            st.query_params["dashboard"] = "1"
            st.rerun()
        else:
            st.error("Der Zugriffs-Link ist ungültig oder abgelaufen. Bitte öffne das Dashboard erneut über deine Streamdex Desktop-App.")

    # 2. Prüfen ob Streamer eingeloggt ist
    authed_tid = st.session_state.get("authenticated_tid")
    if authed_tid:
        started = st.session_state.setdefault("authenticated_at", time.time())
        if time.time() - started > SESSION_MAX_AGE_S:
            for k in ("authenticated_tid", "authenticated_at", "auth_method", "twitch_profile", "acct_data"):
                st.session_state.pop(k, None)
            st.session_state["session_expired"] = True
            st.session_state["dashboard_reauth_required"] = True
            authed_tid = None

    if authed_tid:
        hero.markdown(
            '<div class="sd-hero">'
            '<div class="sd-hero-kicker"><span class="sd-hero-dot"></span> STREAMDEX OS <span class="sd-hero-slash">/</span> CREATOR CONTROL CENTER</div>'
            '<h1 class="sd-hero-title">Dein Streamer-Dashboard</h1>'
            '<p class="sd-hero-description">Dein Stream. Deine Zahlen. Deine Community – alles an einem Ort.</p>'
            '<div class="sd-hero-tags"><span>📈 Kanal-Insights</span><span>🎮 Deine Tools</span><span>🎉 Community-Events</span><span>💬 Direkter Support</span></div>'
            '</div>',
            unsafe_allow_html=True,
        )
    else:
        hero.markdown(
            '<div class="sd-hero sd-hero-welcome">'
            '<div class="sd-hero-kicker"><span class="sd-hero-dot"></span> STREAMDEX OS <span class="sd-hero-slash">/</span> CREATOR SPACE</div>'
            '<h1 class="sd-hero-title">Willkommen bei StreamDex OS</h1>'
            '<p class="sd-hero-description">Das zentrale Control Center für deinen Stream – von Statistiken bis Community-Events.</p>'
            '<div class="sd-hero-tags"><span>🟣 Twitch-Login</span><span>📊 Statistiken</span><span>🎉 Events & Community</span><span>🧰 Downloads & Beta</span></div>'
            '</div>',
            unsafe_allow_html=True,
        )

    if not authed_tid:
        hero.empty()  # Die Dashboard-Headline wird durch die öffentliche Referenz-Landingpage ersetzt.
        if st.session_state.pop("session_expired", False):
            st.warning(f"⏱️ Deine Sitzung ist nach {SESSION_MAX_AGE_S // 3600} Stunden aus Sicherheitsgründen abgelaufen. "
                       "Bitte melde dich erneut mit Twitch an oder öffne das Dashboard über deine Streamdex Desktop-App.")
        elif st.session_state.get("acct_deleted") is not None:
            st.session_state.pop("acct_deleted", None)
            st.success("✅ Deine Daten wurden gelöscht und du wurdest abgemeldet.")
        notice = st.session_state.pop("twitch_login_notice", None)
        if notice:
            st.error(notice)
        if str(st.query_params.get("planner", "")) == "1":
            st.info("Der Planner ist Teil deines Streamer-Dashboards. Melde dich unten mit Twitch an und öffne danach den Reiter „▣ Planner“.")
        if str(st.query_params.get("profile", "")) == "1":
            st.info("Dein Creator-Profil kannst du nach dem Twitch-Login erstellen und veröffentlichen. Klicke danach erneut auf „Profile“ oder öffne den Reiter „♙ Profil“.")
        if str(st.query_params.get("feedback", "")) == "1":
            st.info("Melde dich mit Twitch an, um Vorschläge einzureichen, Community-Umfragen zu erstellen und abzustimmen.")
        for _suite_key, _suite_label in (("ideas", "StreamDex Ideas"), ("bracket", "StreamDex Bracket"), ("wheel", "StreamDex Wheel"), ("wishlist", "StreamDex Wishlist"), ("quiz", "StreamDex Quiz"), ("clips", "StreamDex Clips"), ("goals", "StreamDex Goals"), ("modlog", "StreamDex ModLog"), ("modteam", "StreamDex ModTeam")):
            if str(st.query_params.get(_suite_key, "")) == "1":
                st.info(f"Melde dich mit Twitch an, um {_suite_label} zu öffnen.")
                break
        if str(st.query_params.get("tour", "")) == "1":
            render_guided_tour(authenticated=False)
            return
        _render_landing()
        return

    # Daten des authentifizierten Streamers laden. Twitch-Profil stammt aus Helix,
    # nachdem der OAuth-Code und das User-Access-Token serverseitig validiert wurden.
    presence_ref = db.reference(f"presence/{authed_tid}")
    presence = presence_ref.get() or {}
    oidc_logged_in = st.session_state.get("auth_method") == "twitch"
    twitch_profile = st.session_state.get("twitch_profile", {}) or {}
    oidc_tid = str(authed_tid) if oidc_logged_in else ""
    oidc_username = str(
        twitch_profile.get("display_name")
        or twitch_profile.get("login")
        or ""
    ).strip()
    oidc_picture = str(twitch_profile.get("picture") or "").strip()

    if not presence:
        if oidc_logged_in and oidc_tid == str(authed_tid):
            initial_profile = {
                "twitch_username": oidc_username or str(authed_tid),
                "status": "offline",
                "registered_via": "twitch_web_login",
            }

            def _create_profile_if_missing(current):
                return current if isinstance(current, dict) and current else initial_profile

            presence_ref.transaction(_create_profile_if_missing)
            presence = presence_ref.get() or initial_profile
        else:
            st.error("Konto-Daten konnten nicht geladen werden. Bitte melde dich erneut mit Twitch an oder öffne das Dashboard über deine StreamDex Desktop-App.")
            return

    if oidc_username and not presence.get("twitch_username"):
        presence_ref.child("twitch_username").set(oidc_username)
        presence["twitch_username"] = oidc_username

    twitch_username = presence.get("twitch_username") or oidc_username or authed_tid
    if oidc_logged_in:
        _record_web_login(authed_tid, twitch_profile, st.session_state.get("authenticated_at"))
    app_version = presence.get("app_version", "?")
    last_seen = presence.get("last_seen")
    is_online = presence.get("status") == "online" and last_seen and (time.time() * 1000 - last_seen) < 150000

    have_games = owned_games(authed_tid)
    beta_info = db.reference(f"shop/beta/{authed_tid}").get() or {}
    stats_data = db.reference(f"stats/{authed_tid}").get() or {}

    # Profilkopf: Name, Anmeldestatus und Abmelden bleiben funktional erhalten.
    with st.container(key="sd_profile_header"):
        profile_col, details_col, logout_col = st.columns([0.75, 4.85, 1.4], vertical_alignment="center")
        if oidc_picture:
            try:
                profile_col.image(oidc_picture, width=60)
            except Exception:
                profile_col.markdown("🟣")
        else:
            profile_col.markdown("🟣")

        details_col.markdown(f"### {twitch_username}")
        details_col.markdown(
            f'<span class="sd-profile-status {"online" if is_online else "offline"}">'
            f'{"● ONLINE" if is_online else "● OFFLINE"}</span>',
            unsafe_allow_html=True,
        )
        details_col.caption(f"Twitch-Profil · ID {authed_tid}")
        details_col.caption("Mit Twitch angemeldet" if oidc_logged_in else "Mit StreamDex Desktop-App angemeldet")

        if logout_col.button("🚪 Abmelden", key="dash_logout", use_container_width=True):
            for key in (
                "authenticated_tid", "authenticated_at", "auth_method", "twitch_profile",
                "twitch_oauth_tid", "twitch_oauth_access_token", "twitch_oauth_refresh_token",
                "twitch_oauth_expires_at", "twitch_oauth_scopes",
                "acct_data", "dashboard_reauth_required",
            ):
                st.session_state.pop(key, None)
            st.query_params.clear()
            st.query_params["dashboard"] = "1"
            st.rerun()

    st.divider()

    # Einheitliche Schnellnavigation bleibt auch in den Einzelansichten aller Werkzeuge sichtbar.
    suite_routes = ("ideas", "bracket", "wheel", "wishlist", "quiz", "goals", "modlog", "modteam")
    nav_route = next(
        (route for route in ("radar", "insight", "planner", "clips", "feedback", "community", "profile", "tour", *suite_routes)
         if str(st.query_params.get(route, "")) == "1"),
        "dashboard",
    )
    if nav_route in suite_routes:
        nav_route = "ideas"
    elif nav_route == "insight":
        nav_route = "radar"
    render_os_navigation(nav_route)

    # Support-Nachrichten einmal laden (Banner oben und Tab "Support-Chat" nutzen dieselben Daten).
    # Bewusst ein Banner statt Zähler im Tab-Titel: ändert sich der Titel, springt Streamlit zurück auf den ersten Tab.
    msgs = _load_messages(authed_tid)
    support_last_read = _support_last_read(authed_tid)
    unread = _unread_admin(msgs, support_last_read)
    if unread:
        n_un = len(unread)
        b_text, b_btn = st.columns([4, 1])
        b_text.info(f"💬 **{n_un} neue {'Antwort' if n_un == 1 else 'Antworten'}** vom Support – "
                    "lies sie im Tab „Support-Chat“.")
        if b_btn.button("✔ Gelesen", key="support_mark_read", use_container_width=True):
            _mark_support_read(authed_tid, msgs)
            st.rerun()

    # Der geführte Rundgang ist sowohl aus der Schnellnavigation als auch direkt erreichbar.
    if str(st.query_params.get("tour", "")) == "1":
        render_guided_tour(authenticated=True, username=twitch_username)
        return

    # Direkter Feedback-Link: nur für angemeldete Streamer öffnen.
    if str(st.query_params.get("feedback", "")) == "1":
        _record_tool_use(authed_tid, "feedback")
        back_col, _ = st.columns([1, 5])
        if back_col.button("← Zur Dashboard-Übersicht", key="feedback_back_to_dashboard"):
            st.query_params.clear()
            st.query_params["dashboard"] = "1"
            st.rerun()
        render_feedback_hub(authed_tid, twitch_username)
        return

    # Direkte Links zu den StreamDex-Suite-Werkzeugen.
    _suite_routes = ("ideas", "bracket", "wheel", "wishlist", "quiz", "clips", "goals", "modlog", "modteam")
    _active_suite_tool = next((name for name in _suite_routes if str(st.query_params.get(name, "")) == "1"), None)
    if _active_suite_tool:
        _record_tool_use(authed_tid, _active_suite_tool)
        back_col, _ = st.columns([1, 5])
        if back_col.button("← Zur Dashboard-Übersicht", key=f"suite_back_{_active_suite_tool}"):
            st.query_params.clear()
            st.query_params["dashboard"] = "1"
            st.rerun()
        render_streamdex_suite(authed_tid, twitch_username, _active_suite_tool)
        return

    # Direkter Radar-Link: nur für angemeldete Streamer öffnen.
    if str(st.query_params.get("radar", "")) == "1" or str(st.query_params.get("insight", "")) == "1":
        _record_tool_use(authed_tid, "radar")
        back_col, _ = st.columns([1, 5])
        if back_col.button("← Zur Dashboard-Übersicht", key="radar_back_to_dashboard"):
            st.query_params.clear()
            st.query_params["dashboard"] = "1"
            st.rerun()
        render_radar(authed_tid, twitch_username, _twitch_authorization_url()[0])
        return

    # Direkter Profileditor: nur nach erfolgreichem Streamer-Login öffnen.
    if str(st.query_params.get("profile", "")) == "1":
        _record_tool_use(authed_tid, "profile")
        back_col, _ = st.columns([1, 5])
        if back_col.button("← Zur Dashboard-Übersicht", key="profile_back_to_dashboard"):
            st.query_params.clear()
            st.query_params["dashboard"] = "1"
            st.rerun()
        render_creator_profile(authed_tid, twitch_username)
        return

    # Direkter Planner-Link: nur nach erfolgreichem Streamer-Login öffnen.
    if str(st.query_params.get("planner", "")) == "1":
        _record_tool_use(authed_tid, "planner")
        back_col, _ = st.columns([1, 5])
        if back_col.button("← Zur Dashboard-Übersicht", key="planner_back_to_dashboard"):
            st.query_params.clear()
            st.query_params["dashboard"] = "1"
            st.rerun()
        render_planner(authed_tid, twitch_username, _twitch_authorization_url()[0])
        return

    # Zusätzliche Creator-Bereiche können auch direkt über die URL geöffnet werden.
    if str(st.query_params.get("legacy", "")) == "1":
        _record_tool_use(authed_tid, "legacy")
        back_col, _ = st.columns([1, 5])
        if back_col.button("← Zur Dashboard-Übersicht", key="legacy_back_to_dashboard"):
            st.query_params.clear()
            st.query_params["dashboard"] = "1"
            st.rerun()
        render_legacy(authed_tid, twitch_username)
        return
    if str(st.query_params.get("clips", "")) == "1":
        _record_tool_use(authed_tid, "clips")
        back_col, _ = st.columns([1, 5])
        if back_col.button("← Zur Dashboard-Übersicht", key="clips_back_to_dashboard"):
            st.query_params.clear()
            st.query_params["dashboard"] = "1"
            st.rerun()
        render_clips_manager(authed_tid, twitch_username)
        return
    if str(st.query_params.get("community", "")) == "1":
        _record_tool_use(authed_tid, "events")
        back_col, _ = st.columns([1, 5])
        if back_col.button("← Zur Dashboard-Übersicht", key="community_back_to_dashboard"):
            st.query_params.clear()
            st.query_params["dashboard"] = "1"
            st.rerun()
        render_community_integrations(authed_tid, twitch_username)
        render_event_manager(authed_tid, twitch_username)
        return

    # Große Kachel-Navigation statt kleiner Reiter
    with st.container(key="sd_main_nav"):
        t_over, t_games, t_radar, t_legacy, t_clips, t_feedback, t_suite, t_stats, t_hist, t_gw, t_events, t_planner, t_profile, t_downloads, t_support, t_acct = st.tabs([
            "🏠 Übersicht",
            "🎮 Freigeschaltete Games",
            "📊 StreamDex Insight",
            "📜 Legacy – Chronik",
            "🎬 Clips",
            "💬 Feedback",
            "🧩 Ideas & Tools",
            "📈 Kanal-Statistiken",
            "📅 Verlauf",
            "🎁 Giveaways",
            "🤝 Community & Events",
            "▣ Planner",
            "♙ Profil",
            "📥 Downloads & Beta",
            "💬 Support-Chat",
            "🧾 Konto & Datenschutz",
        ])

    # --- StreamDex Radar ---
    with t_radar:
        render_radar(authed_tid, twitch_username, _twitch_authorization_url()[0])

    # --- StreamDex Legacy: private Community-Chronik ---
    with t_legacy:
        render_legacy(authed_tid, twitch_username)

    # --- StreamDex Clips: Twitch-Import und private Sammlung ---
    with t_clips:
        render_clips_manager(authed_tid, twitch_username)

    # --- StreamDex Feedback ---
    with t_feedback:
        render_feedback_hub(authed_tid, twitch_username)

    # --- StreamDex Ideas und Werkzeug-Hub ---
    with t_suite:
        render_streamdex_suite(authed_tid, twitch_username, "ideas")

    # --- Tab 0: Übersicht ---
    with t_over:
        # Beta-Builds ("BETA VERSION V2") haben keine Release-Nummer: Vergleich mit der öffentlichen Release würde falsch warnen
        _upd = None if "beta" in str(app_version).lower() else _update_notice(app_version)
        if _upd:
            st.info(f"🔔 **Neue Version verfügbar: {_upd[0]}** (du nutzt {app_version}). "
                    "Die App bietet das Update beim Start an, oder du lädst es hier herunter.")
            st.link_button("⬇️ Zur neuen Version", _upd[1])
        try:    # Lurk-App: gleiche Prüfung gegen die neueste Lurk-Release
            _lp = db.reference(f"lurk/presence/{authed_tid}").get()
            if isinstance(_lp, dict):
                _lupd = update_notice(lurk_repo(), _lp.get("app_version"))
                if _lupd:
                    st.info(f"🔔 **Neue Lurk-Version verfügbar: {_lupd[0]}** (du nutzt {_lp.get('app_version', '?')}). "
                            "Die Lurk-App bietet das Update beim Start an, oder du lädst es hier herunter.")
                    st.link_button("⬇️ Zur neuen Lurk-Version", _lupd[1])
        except Exception:
            pass
        render_first_steps(authed_tid)
        st.markdown(OVERVIEW_CSS + _overview_html(presence, stats_data, games, have_games, beta_info, is_online),
                    unsafe_allow_html=True)
        if beta_info:
            try:
                _cfg = download_settings()
                _rev = int(_cfg.get("beta_rev") or 0)
                if _rev and _rev > int(db.reference(f"beta_seen/{authed_tid}").get() or 0):
                    _n = str(_cfg.get("beta_note") or "").strip()
                    st.success("🧪 **Neuer Beta-Build verfügbar!**" + (f" {_n}" if _n else ""))
                    _b1, _b2 = st.columns(2)
                    if beta_link(_cfg):
                        _b1.link_button("⬇️ Neuen Beta-Build laden", beta_link(_cfg), type="primary", use_container_width=True)
                    if _b2.button("✔ Gelesen", key="beta_seen_btn", use_container_width=True):
                        db.reference(f"beta_seen/{authed_tid}").set(_rev)
                        st.rerun()
            except Exception:
                pass
            st.markdown("**🧪 Downloads für Beta-Tester**")
            try:
                render_member_downloads()
            except Exception:
                st.caption("Download-Links gerade nicht erreichbar.")
        if any(g not in have_games for g in games):
            st.link_button("🛒 Weitere Games im Shop freischalten", f"/?u={urllib.parse.quote(str(twitch_username))}")

    # --- Tab 1: Games ---
    with t_games:
        st.subheader("🎮 Deine Games & Features")
        cols = st.columns(3)
        for idx, (g_key, g_name) in enumerate(games.items()):
            is_unlocked = g_key in have_games
            with cols[idx % 3]:
                with st.container(border=True):
                    if is_unlocked:
                        st.markdown(f"### {g_name}")
                        st.markdown('<span class="badge">✅ Freigeschaltet</span>', unsafe_allow_html=True)
                    else:
                        st.markdown(f"### {g_name}")
                        st.markdown('<span class="badge save" style="background:#ef444422;color:#f87171;">🔒 Gesperrt</span>', unsafe_allow_html=True)
                        st.link_button("🛒 Im Shop freischalten", f"/?u={twitch_username}", use_container_width=True)

    # --- Tab 2: Stats ---
    with t_stats:
        st.subheader("📈 Deine Streamdex-Statistiken")
        if not stats_data:
            render_empty_state(
                "Deine Statistiken warten auf Daten",
                "Sobald deine StreamDex-App Aktivität erfasst hat, erscheinen hier deine Kennzahlen. Lass die App laufen und schau später wieder vorbei.",
                "📈",
            )
        else:
            s_cols = st.columns(3)
            for i, (k, label) in enumerate(STAT_KEYS.items()):
                val = int(stats_data.get(k) or 0)
                s_cols[i % 3].metric(label, f"{val:,}".replace(",", "."))

    # --- Tab 3: Verlauf ---
    with t_hist:
        st.subheader("📅 Verlauf")
        history = _load_history(authed_tid)
        if len(history) < 2:
            render_empty_state(
                "Dein Verlauf startet hier",
                "StreamDex speichert den Verlauf täglich. Sobald mindestens zwei Tage mit Daten vorliegen, kannst du Trends und Veränderungen vergleichen.",
                "🗓️",
            )
        else:
            col_a, col_b = st.columns([2, 1])
            h_key = col_a.selectbox("Kennzahl", list(HISTORY_LABELS), format_func=lambda k: HISTORY_LABELS[k], key="hist_key")
            h_days = col_b.radio("Zeitraum", [7, 30, 90], index=1, format_func=lambda d: f"{d} Tage", horizontal=True, key="hist_days")
            series = _daily_series(history, h_key, h_days)
            total = int(series.sum())
            m1, m2, m3 = st.columns(3)
            m1.metric(f"Summe ({h_days} Tage)", _de(total))
            m2.metric("Ø pro Tag", f"{total / h_days:.1f}".replace(".", ","))
            m3.metric("Bester Tag", f"{series.idxmax():%d.%m.} · {_de(int(series.max()))}" if total else "–")
            st.bar_chart(series, height=300)
            st.caption("Tage, an denen die App nicht lief, zeigen 0 – ihre Aktivität wird dem nächsten Tag mit Daten zugerechnet.")

    # --- Tab: Giveaway-Verlauf ---
    with t_gw:
        _render_giveaway_tab(authed_tid)

    # --- Community- und Event-Integrationen ---
    with t_events:
        render_community_integrations(authed_tid, twitch_username)
        st.divider()
        st.markdown("### 🗓️ Events verwalten")
        render_event_manager(authed_tid, twitch_username)

    # --- Planner: persönliche Stream-Planung, Erinnerungen und Twitch-Zeitplan ---
    with t_planner:
        render_planner(authed_tid, twitch_username, _twitch_authorization_url()[0])

    # --- Creator-Profil: privat bearbeiten, optional veröffentlichen ---
    with t_profile:
        render_creator_profile(authed_tid, twitch_username)

    # --- Downloads und Beta: nur sichtbar, nachdem ein Login bestätigt wurde ---
    with t_downloads:
        _render_member_downloads_and_beta(authed_tid, twitch_username, beta_info)

    # --- Tab 5: Support ---
    with t_support:
        st.subheader("💬 Direkt-Support")
        chat_box = st.container(height=400, border=True)
        with chat_box:
            if not msgs:
                st.caption("Noch keine Nachrichten vorhanden.")
            for m in msgs:
                is_admin = m.get("sender") == "admin"
                with st.chat_message("assistant" if is_admin else "user"):
                    _is_new = m in unread
                    st.caption(f"{'🆕 ' if _is_new else ''}{'Support' if is_admin else twitch_username} · {_fmt_ts(m.get('ts'))}")
                    st.write(m.get("text", ""))

        prompt = st.chat_input("Nachricht an den Support senden ...")
        if prompt:
            _send_message(authed_tid, twitch_username, prompt)
            _mark_support_read(authed_tid, msgs)   # wer antwortet, hat die bisherigen Antworten gelesen
            st.rerun()

    # --- Tab 5: Konto & Datenschutz ---
    with t_acct:
        _render_account_tab(authed_tid, twitch_username, bool(is_online))
