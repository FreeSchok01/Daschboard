"""Pure security and privacy helpers shared by StreamDex and its regression tests."""
from copy import deepcopy
import hashlib
import hmac
import re
import secrets
import time

_TWITCH_ID_RE = re.compile(r"^[0-9]{1,15}$")
_FIREBASE_KEY_RE = re.compile(r"^[^.#$\[\]/\x00-\x1f\x7f]{1,768}$")
_OAUTH_NONCE_RE = re.compile(r"^[A-Za-z0-9_-]{16,100}$")


def is_valid_twitch_id(value):
    """Return True only for a Twitch numeric user ID, never a path fragment."""
    return isinstance(value, (str, int)) and bool(_TWITCH_ID_RE.fullmatch(str(value)))


def admin_session_is_valid(authenticated_at, now=None, ttl_seconds=4 * 60 * 60):
    """Validate a server-side admin login timestamp with a strict age window."""
    try:
        started = float(authenticated_at)
        current = float(time.time() if now is None else now)
        ttl = float(ttl_seconds)
    except (TypeError, ValueError, OverflowError):
        return False
    age = current - started
    return started > 0 and ttl > 0 and 0 <= age <= ttl


def make_signed_oauth_state(client_secret, now=None, nonce=None):
    """Create a short-lived, HMAC-signed OAuth state value."""
    timestamp = int(time.time() if now is None else now)
    nonce = nonce or secrets.token_urlsafe(24)
    if not _OAUTH_NONCE_RE.fullmatch(str(nonce)):
        raise ValueError("Invalid OAuth nonce.")
    payload = f"{timestamp}.{nonce}"
    signature = hmac.new(
        str(client_secret).encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return f"{payload}.{signature}"


def verify_signed_oauth_state(state, client_secret, now=None, max_age_seconds=600):
    """Verify OAuth state signature, nonce format, and expiry without leaking details."""
    if not isinstance(state, str):
        return False
    pieces = state.split(".")
    if len(pieces) != 3:
        return False
    timestamp_text, nonce, supplied_signature = pieces
    if not _OAUTH_NONCE_RE.fullmatch(nonce):
        return False
    if not re.fullmatch(r"[0-9]{1,12}", timestamp_text):
        return False
    if not re.fullmatch(r"[0-9a-f]{64}", supplied_signature):
        return False
    try:
        timestamp = int(timestamp_text)
        current = int(time.time() if now is None else now)
        max_age = int(max_age_seconds)
    except (TypeError, ValueError, OverflowError):
        return False
    age = current - timestamp
    if max_age <= 0 or age < -60 or age > max_age:
        return False
    payload = f"{timestamp_text}.{nonce}"
    expected = hmac.new(
        str(client_secret).encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, supplied_signature)


def oauth_state_key(state):
    """Return a database-safe digest; the raw OAuth state must never be stored."""
    return hashlib.sha256(str(state).encode("utf-8")).hexdigest()


def oauth_state_record_is_active(record, now_ms=None):
    """Check a pending-state record before atomically consuming it."""
    if not isinstance(record, dict) or record.get("consumed"):
        return False
    try:
        now = int(time.time() * 1000 if now_ms is None else now_ms)
        issued = int(record.get("issued_at_ms") or 0)
        expires = int(record.get("expires_at_ms") or 0)
    except (TypeError, ValueError, OverflowError):
        return False
    return issued > 0 and issued <= now + 60_000 and expires >= now and expires > issued


def _dict(value):
    return value if isinstance(value, dict) else {}


def _safe_record_without_peer_votes(record):
    """Keep a user's own contribution, but not other members' individual voter IDs."""
    result = deepcopy(_dict(record))
    votes = result.pop("votes", None)
    if isinstance(votes, dict):
        result["vote_count"] = len(votes)
    return result


def collect_user_shared_data(tid, roots):
    """Build a portable export containing only this user's data in shared collections."""
    tid = str(tid or "")
    if not is_valid_twitch_id(tid):
        raise ValueError("Invalid Twitch user ID.")

    roots = _dict(roots)
    exported = {}

    feedback_submitted, feedback_votes = {}, {}
    for key, item in _dict(roots.get("feedback_inbox")).items():
        item = _dict(item)
        if not item:
            continue
        if str(item.get("tid") or "") == tid:
            feedback_submitted[str(key)] = _safe_record_without_peer_votes(item)
        elif tid in _dict(item.get("votes")):
            feedback_votes[str(key)] = {
                "title": str(item.get("title") or ""),
                "vote": deepcopy(item["votes"][tid]),
            }
    if feedback_submitted or feedback_votes:
        exported["feedback"] = {"submitted": feedback_submitted, "votes": feedback_votes}

    wishlist_created, wishlist_votes = {}, {}
    for key, item in _dict(roots.get("streamdex_community_wishlist")).items():
        item = _dict(item)
        if not item:
            continue
        if str(item.get("author_tid") or "") == tid:
            wishlist_created[str(key)] = _safe_record_without_peer_votes(item)
        if tid in _dict(item.get("votes")):
            wishlist_votes[str(key)] = {
                "title": str(item.get("title") or ""),
                "vote": deepcopy(item["votes"][tid]),
            }
    if wishlist_created or wishlist_votes:
        exported["wishlist"] = {"created": wishlist_created, "votes": wishlist_votes}

    polls_created, poll_votes = {}, {}
    for key, item in _dict(roots.get("community_polls")).items():
        item = _dict(item)
        if not item:
            continue
        options = item.get("options") or []
        if isinstance(options, dict):
            options = [options[k] for k in sorted(options, key=str)]
        if str(item.get("created_by") or "") == tid:
            polls_created[str(key)] = _safe_record_without_peer_votes(item)
        votes = _dict(item.get("votes"))
        if tid in votes:
            selected = votes[tid]
            selected_label = None
            try:
                index = int(selected)
                if 0 <= index < len(options):
                    selected_label = str(options[index])
            except (TypeError, ValueError, IndexError):
                pass
            poll_votes[str(key)] = {
                "question": str(item.get("question") or ""),
                "selected_index": selected,
                "selected_option": selected_label,
            }
    if polls_created or poll_votes:
        exported["polls"] = {"created": polls_created, "votes": poll_votes}

    quizzes_created, quiz_answers = {}, {}
    for key, item in _dict(roots.get("streamdex_quiz_rooms")).items():
        item = _dict(item)
        if not item:
            continue
        answers = _dict(item.get("answers"))
        if str(item.get("created_by") or "") == tid:
            sanitized = deepcopy(item)
            sanitized.pop("answers", None)
            sanitized["participant_answer_sets"] = len(answers)
            quizzes_created[str(key)] = sanitized
        if tid in answers:
            user_answers = deepcopy(_dict(answers.get(tid)))
            quiz_answers[str(key)] = {
                "title": str(item.get("title") or ""),
                "answers": user_answers,
            }
    if quizzes_created or quiz_answers:
        exported["quizzes"] = {"created": quizzes_created, "your_answers": quiz_answers}

    events_created, event_registrations = {}, {}
    for key, item in _dict(roots.get("streamdex_events")).items():
        item = _dict(item)
        if not item:
            continue
        participants = _dict(item.get("participants"))
        if str(item.get("owner_tid") or "") == tid:
            sanitized = deepcopy(item)
            sanitized.pop("participants", None)
            sanitized["participant_count"] = len(participants)
            events_created[str(key)] = sanitized
        for participant_id, participant in participants.items():
            if str(_dict(participant).get("registrant_tid") or "") == tid or str(participant_id) == tid:
                event_registrations[str(key)] = {
                    "event_id": str(key),
                    "title": str(item.get("title") or ""),
                    "event_date": str(item.get("event_date") or ""),
                    "registration": deepcopy(_dict(participant)),
                }
    if events_created or event_registrations:
        exported["events"] = {"created": events_created, "your_registrations": event_registrations}

    return exported


def plan_shared_account_deletions(tid, roots):
    """Return only RTDB paths owned by this account or its votes/answers/registrations."""
    tid = str(tid or "")
    if not is_valid_twitch_id(tid):
        raise ValueError("Invalid Twitch user ID.")
    roots = _dict(roots)
    targets = []

    def safe_key(value):
        return isinstance(value, (str, int)) and bool(_FIREBASE_KEY_RE.fullmatch(str(value)))

    specs = (
        ("feedback_inbox", "tid", "votes"),
        ("streamdex_community_wishlist", "author_tid", "votes"),
        ("community_polls", "created_by", "votes"),
        ("streamdex_quiz_rooms", "created_by", "answers"),
    )
    for root, owner_field, child_field in specs:
        records = _dict(roots.get(root))
        for key, item in records.items():
            if not safe_key(key) or not isinstance(item, dict):
                continue
            if str(item.get(owner_field) or "") == tid:
                targets.append(f"{root}/{key}")
            elif tid in _dict(item.get(child_field)):
                targets.append(f"{root}/{key}/{child_field}/{tid}")

    for key, event in _dict(roots.get("streamdex_events")).items():
        if not safe_key(key) or not isinstance(event, dict):
            continue
        if str(event.get("owner_tid") or "") == tid:
            targets.append(f"streamdex_events/{key}")
            continue
        participants = _dict(event.get("participants"))
        if str(tid) in participants:
            targets.append(f"streamdex_events/{key}/participants/{tid}")
        for participant_id, participant in participants.items():
            if safe_key(participant_id) and str(_dict(participant).get("registrant_tid") or "") == tid:
                targets.append(f"streamdex_events/{key}/participants/{participant_id}")

    return list(dict.fromkeys(targets))


def safe_exception_label(exc):
    """Return only an exception class name, never a message that may contain secrets."""
    return type(exc).__name__ if exc is not None else "UnknownError"
