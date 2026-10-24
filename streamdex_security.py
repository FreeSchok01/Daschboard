"""Shared, dependency-free security checks for StreamDex account-scoped features.

Firebase Admin SDK bypasses Realtime Database security rules. Every private renderer
must therefore validate the server-side Streamlit session before touching user data.
"""
from __future__ import annotations

import hmac
import re
import time
from typing import Mapping, Any

TID_PATTERN = re.compile(r"^[0-9]{1,15}$")
USER_SESSION_MAX_AGE_SECONDS = 2 * 60 * 60

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
