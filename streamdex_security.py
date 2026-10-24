"""Shared, dependency-free security checks for StreamDex account-scoped features.

Firebase Admin SDK bypasses Realtime Database security rules. Every private renderer
must therefore validate the server-side Streamlit session before touching user data.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import time
from typing import Mapping, Any

TID_PATTERN = re.compile(r"^[0-9]{1,15}$")
USER_SESSION_MAX_AGE_SECONDS = 2 * 60 * 60
ADMIN_SESSION_MAX_AGE_SECONDS = 4 * 60 * 60

# Delete account-owned data first; presence must be removed last so a failed deletion
# does not make the account impossible to find and retry.
ACCOUNT_DELETE_PATHS = (
    "stats/{t}",
    "stats_history/{t}",
    "chats/{t}",
    "chat_meta/{t}",
    "gifts/{t}",
    "lurk/stats/{t}",
    "lurk/chats/{t}",
    "lurk/chat_meta/{t}",
    "lurk/presence/{t}",
    "support_read/{t}",
    "giveaway_log/{t}",
    "radar_watchlists/{t}",
    "radar_analytics/{t}",
    "streamdex_planner/{t}",
    "streamdex_clips/{t}",
    "streamdex_ideas/{t}",
    "streamdex_brackets/{t}",
    "streamdex_wheel/{t}",
    "streamdex_goals/{t}",
    "streamdex_modlog/{t}",
    "streamdex_modteam/{t}",
    "streamdex_web_auth/{t}",
    "streamdex_tool_usage/{t}",
    "beta_seen/{t}",
    "creator_profiles/{t}",
    "presence/{t}",  # Keep this last.
)

# Retained by design: entitlements/purchase records and abuse-prevention overrides.
ACCOUNT_KEEP_PATHS = (
    "tour_skip/{t}",
    "shop/beta/{t}",
    "game_flags/streamers/{t}",
)


def is_valid_twitch_id(value: object) -> bool:
    """Accept a numeric Twitch user ID only; never silently sanitize path input."""
    return isinstance(value, (str, int)) and bool(TID_PATTERN.fullmatch(str(value)))


def account_path(template: str, twitch_id: object) -> str:
    """Format an account path only after strictly validating its Twitch ID."""
    if not is_valid_twitch_id(twitch_id):
        raise ValueError("Ungültige Twitch-ID.")
    if "{t}" not in template:
        raise ValueError("Ungültige Kontopfad-Vorlage.")
    return template.format(t=str(twitch_id))


def has_active_user_session(
    session_state: Mapping[str, Any],
    requested_tid: object,
    now: float | None = None,
) -> bool:
    """Return whether the current server-side session owns a valid, unexpired account."""
    if not is_valid_twitch_id(requested_tid):
        return False

    session_tid = str(session_state.get("authenticated_tid") or "")
    if not is_valid_twitch_id(session_tid):
        return False
    if not hmac.compare_digest(str(requested_tid), session_tid):
        return False
    if session_state.get("auth_method") not in {"twitch", "desktop"}:
        return False

    try:
        started = float(session_state.get("authenticated_at") or 0)
    except (TypeError, ValueError, OverflowError):
        return False
    current = time.time() if now is None else float(now)
    age = current - started
    return started > 0 and 0 <= age <= USER_SESSION_MAX_AGE_SECONDS



def has_active_admin_session(
    session_state: Mapping[str, Any],
    now: float | None = None,
) -> bool:
    """Validate the fixed maximum lifetime of the shared-password admin session."""
    if not session_state.get("auth_ok"):
        return False
    try:
        started = float(session_state.get("admin_authenticated_at") or 0)
    except (TypeError, ValueError, OverflowError):
        return False
    current = time.time() if now is None else float(now)
    age = current - started
    return started > 0 and 0 <= age <= ADMIN_SESSION_MAX_AGE_SECONDS



def create_signed_oauth_state(client_secret: str, nonce: str, now: float | None = None) -> str:
    """Create a timestamped HMAC state value for the Twitch OAuth redirect."""
    if not isinstance(nonce, str) or not re.fullmatch(r"[A-Za-z0-9_-]{16,100}", nonce):
        raise ValueError("Ungültiger OAuth-Nonce.")
    timestamp = str(int(time.time() if now is None else now))
    payload = f"{timestamp}.{nonce}"
    signature = hmac.new(
        str(client_secret).encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload}.{signature}"


def validate_signed_oauth_state(
    state: object,
    client_secret: str,
    max_age_seconds: int = 600,
    now: float | None = None,
) -> bool:
    """Constant-time HMAC check plus strict nonce, age, and future-skew validation."""
    if not isinstance(state, str) or not 1 <= int(max_age_seconds) <= 3600:
        return False
    pieces = state.split(".")
    if len(pieces) != 3:
        return False
    timestamp_text, nonce, supplied_signature = pieces
    if not re.fullmatch(r"[0-9]{1,12}", timestamp_text):
        return False
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,100}", nonce):
        return False
    if not re.fullmatch(r"[0-9a-f]{64}", supplied_signature):
        return False
    timestamp = int(timestamp_text)
    current = time.time() if now is None else float(now)
    age = current - timestamp
    if age < -60 or age > int(max_age_seconds):
        return False
    payload = f"{timestamp_text}.{nonce}"
    expected = hmac.new(
        str(client_secret).encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, supplied_signature)
