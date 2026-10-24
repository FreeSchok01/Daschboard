"""Regression tests for StreamDex's most sensitive user flows.

All Firebase access is mocked and every Twitch HTTP response is stubbed. These
tests never contact real Twitch accounts or modify production Firebase data.
"""
import copy
import json
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

import events
import feedback_hub
import onboarding
import streamdex_suite
import streamer_dashboard


class MemoryDatabase:
    """Tiny Firebase-like in-memory tree with query and failure injection support."""

    def __init__(self):
        self.root = {}
        self.fail_get = set()
        self.fail_set = set()
        self.fail_delete = set()
        self._counter = 0

    @staticmethod
    def _parts(path):
        return [part for part in str(path or "").strip("/").split("/") if part]

    @staticmethod
    def _resolve_server_values(value):
        if isinstance(value, dict):
            if value == {".sv": "timestamp"}:
                return int(time.time() * 1000)
            return {key: MemoryDatabase._resolve_server_values(item) for key, item in value.items()}
        if isinstance(value, list):
            return [MemoryDatabase._resolve_server_values(item) for item in value]
        return copy.deepcopy(value)

    def reference(self, path=""):
        return MemoryReference(self, str(path or "").strip("/"))

    def _get(self, path):
        if path in self.fail_get:
            raise PermissionError("mock read denied")
        value = self.root
        for part in self._parts(path):
            if not isinstance(value, dict) or part not in value:
                return None
            value = value[part]
        return copy.deepcopy(value)

    def _set(self, path, value):
        if path in self.fail_set:
            raise PermissionError("mock write denied")
        parts = self._parts(path)
        if not parts:
            self.root = self._resolve_server_values(value)
            return
        parent = self.root
        for part in parts[:-1]:
            existing = parent.get(part)
            if not isinstance(existing, dict):
                existing = {}
                parent[part] = existing
            parent = existing
        parent[parts[-1]] = self._resolve_server_values(value)

    def _delete(self, path):
        if path in self.fail_delete:
            raise PermissionError("mock delete denied")
        parts = self._parts(path)
        if not parts:
            self.root = {}
            return
        parent = self.root
        for part in parts[:-1]:
            if not isinstance(parent, dict) or part not in parent:
                return
            parent = parent[part]
        if isinstance(parent, dict):
            parent.pop(parts[-1], None)


class MemoryReference:
    def __init__(self, database, path, order_key=None, equal_value=None, limit=None):
        self.database = database
        self.path = path
        self.order_key = order_key
        self.equal_value = equal_value
        self.limit = limit

    def child(self, child_path):
        child_path = str(child_path or "").strip("/")
        path = "/".join(part for part in (self.path, child_path) if part)
        return MemoryReference(self.database, path)

    def get(self):
        value = self.database._get(self.path)
        if not isinstance(value, dict):
            return value
        rows = value
        if self.order_key is not None and self.equal_value is not None:
            rows = {
                key: row for key, row in rows.items()
                if isinstance(row, dict) and str(row.get(self.order_key)) == str(self.equal_value)
            }
        if self.order_key is not None:
            rows = dict(sorted(
                rows.items(),
                key=lambda pair: str(pair[1].get(self.order_key, "")) if isinstance(pair[1], dict) else "",
            ))
        if self.limit is not None:
            rows = dict(list(rows.items())[-self.limit:])
        return copy.deepcopy(rows)

    def set(self, value):
        self.database._set(self.path, value)

    def update(self, values):
        existing = self.database._get(self.path)
        if not isinstance(existing, dict):
            existing = {}
        existing.update(values)
        self.database._set(self.path, existing)

    def delete(self):
        self.database._delete(self.path)

    def transaction(self, update_fn):
        """Emulate Firebase RTDB transactions for deterministic unit tests."""
        current = self.database._get(self.path)
        updated = update_fn(current)
        self.database._set(self.path, updated)
        return updated

    def push(self, value):
        self.database._counter += 1
        key = f"test_push_{self.database._counter}"
        self.child(key).set(value)
        return self.child(key)

    def order_by_child(self, key):
        return MemoryReference(self.database, self.path, order_key=key, equal_value=self.equal_value, limit=self.limit)

    def equal_to(self, value):
        return MemoryReference(self.database, self.path, order_key=self.order_key, equal_value=value, limit=self.limit)

    def limit_to_last(self, value):
        return MemoryReference(self.database, self.path, order_key=self.order_key, equal_value=self.equal_value, limit=value)


@pytest.fixture
def memory_db(monkeypatch):
    database = MemoryDatabase()
    monkeypatch.setattr(streamer_dashboard, "db", database)
    monkeypatch.setattr(feedback_hub, "db", database)
    monkeypatch.setattr(events, "db", database)
    monkeypatch.setattr(streamdex_suite, "db", database)
    return database


def _fake_streamlit(query_params=None, session_state=None):
    return SimpleNamespace(
        query_params=dict(query_params or {}),
        session_state=dict(session_state or {}),
    )


def test_twitch_oauth_state_is_signed_and_rejects_tampering():
    state = streamer_dashboard._make_twitch_state("test-secret")
    assert streamer_dashboard._valid_twitch_state(state, "test-secret")
    assert not streamer_dashboard._valid_twitch_state(state, "wrong-secret")
    assert not streamer_dashboard._valid_twitch_state(state + "x", "test-secret")
    assert not streamer_dashboard._valid_twitch_state("bad-state", "test-secret")


def test_twitch_authorization_url_requests_expected_scopes(monkeypatch):
    monkeypatch.setattr(streamer_dashboard, "db", MemoryDatabase())
    monkeypatch.setattr(streamer_dashboard, "_twitch_credentials", lambda: ("client-id", "test-secret"))
    url, error = streamer_dashboard._twitch_authorization_url()

    assert error is None
    query = parse_qs(urlparse(url).query)
    assert query["client_id"] == ["client-id"]
    assert query["response_type"] == ["code"]
    scopes = set(query["scope"][0].split())
    assert "openid" in scopes
    assert "channel:manage:schedule" in scopes
    assert streamer_dashboard._valid_twitch_state(query["state"][0], "test-secret")


def test_twitch_oauth_callback_keeps_validated_account_in_session_only(monkeypatch, memory_db):
    fake_st = _fake_streamlit({"code": "temporary-code", "state": "valid-state"})
    monkeypatch.setattr(streamer_dashboard, "st", fake_st)
    pending_now = int(time.time() * 1000)
    memory_db.reference(f"streamdex_oauth_states/{streamer_dashboard.oauth_state_key('valid-state')}").set({
        "issued_at_ms": pending_now,
        "expires_at_ms": pending_now + 600_000,
        "consumed": False,
    })
    monkeypatch.setattr(streamer_dashboard, "_twitch_credentials", lambda: ("client-id", "client-secret"))
    monkeypatch.setattr(streamer_dashboard, "_valid_twitch_state", lambda state, secret: state == "valid-state")

    def fake_http(url, method="GET", form=None, headers=None):
        if url == streamer_dashboard.TWITCH_TOKEN_URL:
            assert form["grant_type"] == "authorization_code"
            return {
                "access_token": "unit-test-access-token",
                "refresh_token": "unit-test-refresh-token",
                "expires_in": 3600,
                "scope": ["openid", "channel:manage:schedule"],
            }
        if url == streamer_dashboard.TWITCH_VALIDATE_URL:
            assert headers["Authorization"] == "OAuth unit-test-access-token"
            return {"client_id": "client-id", "user_id": "12345"}
        if url == streamer_dashboard.TWITCH_USERS_URL:
            return {"data": [{
                "id": "12345",
                "login": "testcreator",
                "display_name": "TestCreator",
                "profile_image_url": "https://example.test/avatar.png",
            }]}
        raise AssertionError(f"Unexpected Twitch endpoint: {url}")

    monkeypatch.setattr(streamer_dashboard, "_twitch_http_json", fake_http)

    assert streamer_dashboard.handle_twitch_oauth_callback() is True
    assert fake_st.query_params == {"dashboard": "1"}
    assert fake_st.session_state["authenticated_tid"] == "12345"
    assert fake_st.session_state["twitch_profile"]["login"] == "testcreator"
    assert fake_st.session_state["twitch_oauth_access_token"] == "unit-test-access-token"
    assert fake_st.session_state["twitch_oauth_refresh_token"] == "unit-test-refresh-token"
    assert "channel:manage:schedule" in fake_st.session_state["twitch_oauth_scopes"]
    assert memory_db.reference("streamdex_oauth_states").get() in ({}, None)
    assert "unit-test-access-token" not in json.dumps(memory_db.root)
    assert "unit-test-refresh-token" not in json.dumps(memory_db.root)


def test_twitch_oauth_callback_rejects_invalid_state_with_clear_notice(monkeypatch):
    fake_st = _fake_streamlit({"code": "temporary-code", "state": "forged-state"})
    monkeypatch.setattr(streamer_dashboard, "st", fake_st)
    monkeypatch.setattr(streamer_dashboard, "_twitch_credentials", lambda: ("client-id", "client-secret"))
    monkeypatch.setattr(streamer_dashboard, "_valid_twitch_state", lambda state, secret: False)
    calls = []
    monkeypatch.setattr(streamer_dashboard, "_twitch_http_json", lambda *a, **k: calls.append(a) or {})

    assert streamer_dashboard.handle_twitch_oauth_callback() is True
    assert not calls
    assert "abgelaufen oder ungültig" in fake_st.session_state["twitch_login_notice"]
    assert "authenticated_tid" not in fake_st.session_state
    assert fake_st.query_params == {"dashboard": "1"}


def test_data_access_is_account_scoped_and_reports_unavailable_areas(memory_db):
    memory_db.reference("stats/12345").set({"checkins": 7})
    memory_db.reference("feedback_inbox/fb-own").set({"tid": "12345", "title": "my feedback"})
    memory_db.reference("feedback_inbox/fb-other").set({"tid": "99999", "title": "someone else's feedback"})
    memory_db.reference("streamdex_events/event-own").set({"owner_tid": "12345", "title": "My event"})
    memory_db.reference("streamdex_events/event-other").set({"owner_tid": "99999", "title": "Other event"})

    errors = []
    data = streamer_dashboard._collect_account_data("12345", errors=errors)
    assert errors == []
    assert data["stats/12345"] == {"checkins": 7}
    assert set(data["feedback_inbox (nur deine Einträge)"]) == {"fb-own"}
    assert set(data["streamdex_events (eigene Events)"]) == {"event-own"}

    memory_db.fail_get.add("stats/12345")
    errors = []
    data = streamer_dashboard._collect_account_data("12345", errors=errors)
    assert "stats/12345" not in data
    assert any("Statistiken" in message and "nicht gelesen" in message for message in errors)


def test_account_export_is_valid_json_and_contains_requested_account_only():
    encoded = streamer_dashboard._build_account_export_json(
        "12345",
        {"stats/12345": {"checkins": 7}},
        exported_at="2026-10-24T10:00:00+02:00",
    )
    payload = json.loads(encoded)
    assert payload["twitch_id"] == "12345"
    assert payload["exportiert_am"] == "2026-10-24T10:00:00+02:00"
    assert payload["daten"]["stats/12345"]["checkins"] == 7
    assert "client_secret" not in encoded
    assert "access_token" not in encoded


def test_account_deletion_removes_owned_data_and_preserves_purchase_entitlements(memory_db):
    memory_db.reference("stats/12345").set({"checkins": 7})
    memory_db.reference("stats/99999").set({"checkins": 9})
    memory_db.reference("presence/12345").set({"status": "offline"})
    memory_db.reference("presence/99999").set({"status": "online"})
    memory_db.reference("creator_profiles/12345").set({"slug": "my-creator"})
    memory_db.reference("creator_profile_slugs/my-creator").set("12345")
    memory_db.reference("feedback_inbox/fb-own").set({"tid": "12345", "title": "my feedback"})
    memory_db.reference("feedback_inbox/fb-other").set({"tid": "99999", "title": "other feedback"})
    memory_db.reference("streamdex_events/event-own").set({"owner_tid": "12345", "title": "My event"})
    memory_db.reference("streamdex_events/event-other").set({"owner_tid": "99999", "title": "Other event"})
    memory_db.reference("shop/beta/12345").set({"entitled": True})

    removed, errors = streamer_dashboard._delete_account_data("12345")

    assert removed > 0
    assert errors == []
    assert memory_db.reference("stats/12345").get() is None
    assert memory_db.reference("presence/12345").get() is None
    assert memory_db.reference("creator_profile_slugs/my-creator").get() is None
    assert memory_db.reference("feedback_inbox/fb-own").get() is None
    assert memory_db.reference("streamdex_events/event-own").get() is None
    assert memory_db.reference("stats/99999").get() == {"checkins": 9}
    assert memory_db.reference("presence/99999").get() == {"status": "online"}
    assert memory_db.reference("feedback_inbox/fb-other").get() == {"tid": "99999", "title": "other feedback"}
    assert memory_db.reference("streamdex_events/event-other").get() == {"owner_tid": "99999", "title": "Other event"}
    assert memory_db.reference("shop/beta/12345").get() == {"entitled": True}


def test_partial_account_deletion_returns_actionable_error(memory_db):
    memory_db.reference("stats/12345").set({"checkins": 7})
    memory_db.fail_delete.add("stats/12345")

    _, errors = streamer_dashboard._delete_account_data("12345")

    assert any("Statistiken" in message and "nicht gelöscht" in message for message in errors)


def test_poll_creation_validates_options_and_persists_to_database(memory_db):
    feedback_hub._create_poll("12345", "TestCreator", "Welches Spiel?", ["Minecraft", "  ", "Minecraft", "Stardew Valley"])
    polls = memory_db.reference("community_polls").get()
    assert len(polls) == 1
    poll = next(iter(polls.values()))
    assert poll["question"] == "Welches Spiel?"
    assert poll["options"] == ["Minecraft", "Stardew Valley"]
    assert poll["created_by"] == "12345"

    with pytest.raises(ValueError, match="mindestens zwei"):
        feedback_hub._create_poll("12345", "TestCreator", "Zu wenig?", ["Ja", "Ja"])


def test_poll_creation_enforces_five_open_poll_limit(memory_db):
    for index in range(5):
        memory_db.reference(f"community_polls/poll_{index}").set({
            "question": f"Question {index}",
            "options": ["A", "B"],
            "created_by": "12345",
            "created_at": 1000 + index,
            "closed": False,
            "votes": {},
        })

    with pytest.raises(ValueError, match="maximal fünf"):
        feedback_hub._create_poll("12345", "TestCreator", "Sixth poll?", ["A", "B"])


def test_poll_vote_is_saved_once_per_account_and_closed_polls_cannot_be_changed(memory_db):
    memory_db.reference("community_polls/poll_1").set({
        "question": "Pick one",
        "options": ["Option A", "Option B"],
        "created_by": "99999",
        "created_at": 100,
        "closed": False,
        "votes": {"99999": 1},
    })

    index = feedback_hub._cast_poll_vote("poll_1", "12345", "Option B")
    assert index == 1
    assert memory_db.reference("community_polls/poll_1/votes/12345").get() == 1
    feedback_hub._cast_poll_vote("poll_1", "12345", "Option A")
    assert memory_db.reference("community_polls/poll_1/votes/12345").get() == 0

    with pytest.raises(ValueError, match="verfügbaren Antworten"):
        feedback_hub._cast_poll_vote("poll_1", "12345", "Invalid choice")
    with pytest.raises(ValueError, match="ungültige Kennung"):
        feedback_hub._cast_poll_vote("../poll_1", "12345", "Option A")
    with pytest.raises(ValueError, match="Sitzung ist ungültig"):
        feedback_hub._cast_poll_vote("poll_1", "not-a-twitch-id", "Option A")

    memory_db.reference("community_polls/poll_1").update({"closed": True})
    with pytest.raises(ValueError, match="geschlossen"):
        feedback_hub._cast_poll_vote("poll_1", "12345", "Option A")


def test_guided_onboarding_has_a_clear_first_success_path():
    steps = onboarding.GUIDED_TOUR_STEPS
    assert [step["id"] for step in steps] == ["overview", "first_idea", "planner", "profile"]
    assert steps[1]["route"] == "ideas"
    assert steps[1]["action"] == "Erste Idee anlegen"
    assert steps[2]["route"] == "planner"
    assert all(step["title"] and step["benefit"] and step["description"] for step in steps)




def test_quiz_room_code_reservation_never_overwrites_existing_rooms(monkeypatch, memory_db):
    memory_db.reference("streamdex_quiz_rooms/ABC123").set({
        "code": "ABC123", "created_by": "99999", "title": "Existing room",
    })
    candidates = iter(["ABC123", "DEF456"])
    monkeypatch.setattr(streamdex_suite.secrets, "token_hex", lambda size: next(candidates))
    questions = [{"question": "Example?", "options": ["A", "B"], "correct_index": 0}]

    code = streamdex_suite._create_quiz_room("12345", "TestCreator", "New room", questions)

    assert code == "DEF456"
    assert memory_db.reference("streamdex_quiz_rooms/ABC123/title").get() == "Existing room"
    created = memory_db.reference("streamdex_quiz_rooms/DEF456").get()
    assert created["created_by"] == "12345"
    assert created["title"] == "New room"
    assert created["answers"] == {}


def test_event_mutations_recheck_the_owner_before_writing(memory_db):
    event = {
        "owner_tid": "12345",
        "title": "Owned event",
        "status": "open",
        "capacity": 3,
        "participants": {},
    }
    memory_db.reference("streamdex_events/event_123").set(event)

    assert not events._set_owned_event_status("event_123", "99999", "closed")
    assert memory_db.reference("streamdex_events/event_123/status").get() == "open"
    assert not events._delete_owned_event("event_123", "99999")
    assert memory_db.reference("streamdex_events/event_123").get()["owner_tid"] == "12345"

    assert events._set_owned_event_status("event_123", "12345", "closed")
    assert memory_db.reference("streamdex_events/event_123/status").get() == "closed"
    assert events._set_owned_event_status("event_123", "12345", "open")
    assert events._delete_owned_event("event_123", "12345")
    assert memory_db.reference("streamdex_events/event_123").get() is None


def test_event_registration_checks_status_capacity_and_duplicate_names_atomically(memory_db):
    memory_db.reference("streamdex_events/event_123").set({
        "owner_tid": "12345",
        "title": "Full soon",
        "status": "open",
        "capacity": 1,
        "participants": {},
    })
    events._register_event_participant("event_123", "FirstPerson", "Twitch", "11111")
    saved = memory_db.reference("streamdex_events/event_123/participants").get()
    assert len(saved) == 1
    participant = next(iter(saved.values()))
    assert participant["registrant_tid"] == "11111"

    with pytest.raises(ValueError, match="voll"):
        events._register_event_participant("event_123", "SecondPerson", "Discord", "22222")
    assert len(memory_db.reference("streamdex_events/event_123/participants").get()) == 1

    memory_db.reference("streamdex_events/event_123").update({"capacity": 2})
    with pytest.raises(ValueError, match="bereits angemeldet"):
        events._register_event_participant("event_123", "FirstPerson", "Twitch", "33333")
    with pytest.raises(ValueError, match="StreamDex-Konto"):
        events._register_event_participant("event_123", "ChangedName", "Twitch", "11111")
    assert len(memory_db.reference("streamdex_events/event_123/participants").get()) == 1

    memory_db.reference("streamdex_events/event_123/status").set("closed")
    with pytest.raises(ValueError, match="geschlossen"):
        events._register_event_participant("event_123", "ThirdPerson", "Web", "44444")
