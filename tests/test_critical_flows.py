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

import creator_profile
import events
import feedback_hub
import onboarding
import streamdex_suite
import streamer_dashboard
import shop


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

    def transaction(self, update_fn):
        current = self.database._get(self.path)
        updated = update_fn(current)
        self.database._set(self.path, updated)
        return {"committed": True, "snapshot": updated}

    def update(self, values):
        existing = self.database._get(self.path)
        if not isinstance(existing, dict):
            existing = {}
        existing.update(values)
        self.database._set(self.path, existing)

    def delete(self):
        self.database._delete(self.path)

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
    monkeypatch.setattr(streamdex_suite, "db", database)
    monkeypatch.setattr(events, "db", database)
    monkeypatch.setattr(shop, "db", database)
    monkeypatch.setattr(creator_profile, "db", database)
    return database


def _fake_streamlit(query_params=None, session_state=None):
    return SimpleNamespace(
        query_params=dict(query_params or {}),
        session_state=dict(session_state or {}),
    )



def test_fmt_twitch_started_at_uses_berlin_time():
    assert streamer_dashboard._fmt_twitch_started_at("2026-10-25T10:00:00Z") == "25.10.2026, 11:00 Uhr"
    assert streamer_dashboard._fmt_twitch_started_at("") == "Zeitpunkt unbekannt"
    assert streamer_dashboard._fmt_twitch_started_at("not-a-date") == "Zeitpunkt unbekannt"


def test_own_twitch_stream_status_returns_live_details(monkeypatch):
    streamer_dashboard._load_own_twitch_stream_status.clear()
    monkeypatch.setattr(streamer_dashboard, "_twitch_credentials", lambda: ("client-id", "client-secret"))
    responses = iter([
        {"access_token": "app-token"},
        {"data": [{
            "title": "Test stream", "game_name": "Just Chatting",
            "viewer_count": 42, "started_at": "2026-10-25T10:00:00Z",
        }]},
    ])
    monkeypatch.setattr(streamer_dashboard, "_twitch_http_json", lambda *args, **kwargs: next(responses))

    result = streamer_dashboard._load_own_twitch_stream_status("Test_Channel")

    assert result["available"] is True
    assert result["live"] is True
    assert result["title"] == "Test stream"
    assert result["game"] == "Just Chatting"
    assert result["viewers"] == 42
    assert result["url"] == "https://www.twitch.tv/test_channel"
    streamer_dashboard._load_own_twitch_stream_status.clear()


def test_own_twitch_stream_status_handles_offline_channel(monkeypatch):
    streamer_dashboard._load_own_twitch_stream_status.clear()
    monkeypatch.setattr(streamer_dashboard, "_twitch_credentials", lambda: ("client-id", "client-secret"))
    responses = iter([{"access_token": "app-token"}, {"data": []}])
    monkeypatch.setattr(streamer_dashboard, "_twitch_http_json", lambda *args, **kwargs: next(responses))

    result = streamer_dashboard._load_own_twitch_stream_status("test_channel")

    assert result == {"available": True, "live": False}
    streamer_dashboard._load_own_twitch_stream_status.clear()


def test_twitch_oauth_state_is_signed_and_rejects_tampering():
    state = streamer_dashboard._make_twitch_state("test-secret")
    assert streamer_dashboard._valid_twitch_state(state, "test-secret")
    assert not streamer_dashboard._valid_twitch_state(state, "wrong-secret")
    assert not streamer_dashboard._valid_twitch_state(state + "x", "test-secret")
    assert not streamer_dashboard._valid_twitch_state("bad-state", "test-secret")


def test_twitch_authorization_url_requests_expected_scopes(monkeypatch, memory_db):
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
    monkeypatch.setattr(streamer_dashboard, "_twitch_credentials", lambda: ("client-id", "client-secret"))
    monkeypatch.setattr(streamer_dashboard, "_valid_twitch_state", lambda state, secret: state == "valid-state")
    now_ms = int(time.time() * 1000)
    memory_db.reference(
        f"streamdex_oauth_states/{streamer_dashboard.oauth_state_key('valid-state')}"
    ).set({
        "issued_at_ms": now_ms,
        "expires_at_ms": now_ms + 600_000,
        "consumed": False,
    })

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
    serialized_db = json.dumps(memory_db.root)
    assert "unit-test-access-token" not in serialized_db
    assert "unit-test-refresh-token" not in serialized_db
    assert "temporary-code" not in serialized_db
    assert "valid-state" not in serialized_db  # Only a digest is allowed while a state is pending.


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
    shared = data["community_activity (nur deine Beiträge, Stimmen, Antworten und Anmeldungen)"]
    assert set(shared["feedback"]["submitted"]) == {"fb-own"}
    assert set(shared["events"]["created"]) == {"event-own"}
    assert "fb-other" not in shared["feedback"]["submitted"]
    assert "event-other" not in shared["events"]["created"]

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


def test_shop_module_downloads_require_paid_order_and_matching_twitch_account(monkeypatch, memory_db):
    items = {
        "slot": {"kind": "game", "name": "Slot Machine", "games": ["slot"], "download_url": "https://downloads.example/slot.zip"},
        "arena": {"kind": "game", "name": "Arena", "games": ["arena"], "download_url": "javascript:alert(1)"},
        "pack_casino": {"kind": "pack", "name": "Casino-Pack", "games": ["slot", "hilo"], "download_url": ""},
        "hilo": {"kind": "game", "name": "Hi-Lo", "games": ["hilo"], "download_url": ""},
    }
    memory_db.reference("shop/orders/SDX-ABC234").set({
        "tid": "12345", "status": "paid", "games": ["slot", "arena", "hilo"],
    })
    memory_db.reference("shop/orders/SDX-DEF234").set({
        "tid": "12345", "status": "pending", "games": ["slot"],
    })

    order, links = shop._order_downloads(
        "SDX-ABC234", "12345", items
    )
    assert order["status"] == "paid"
    assert links == [{
        "game": "slot",
        "name": "Slot Machine",
        "url": "https://downloads.example/slot.zip",
    }]
    assert shop._order_downloads("SDX-ABC234", "99999", items) == (None, [])
    assert shop._order_downloads("SDX-DEF234", "12345", items) == (None, [])
    assert shop._order_downloads("../../", "12345", items) == (None, [])


def test_shop_rejects_non_https_download_urls_and_default_catalog_has_download_fields():
    assert shop._safe_download_url("https://example.test/game.zip") == "https://example.test/game.zip"
    assert shop._safe_download_url("javascript:alert(1)") == ""
    assert shop._safe_download_url("http://example.test/game.zip") == ""
    assert shop._safe_download_url("https://user:secret@example.test/game.zip") == ""
    defaults = shop.default_items({"slot": "Slot Machine", "fishing": "Fishing"})
    assert defaults["slot"]["download_url"] == ""
    assert defaults["fishing"]["download_url"] == ""

def test_twitch_login_uses_native_streamlit_external_link(monkeypatch):
    rendered = []
    fake_st = SimpleNamespace(
        link_button=lambda label, url, **kwargs: rendered.append((label, url, kwargs)),
        error=lambda message: pytest.fail(f"Unexpected login error: {message}"),
        info=lambda message: pytest.fail(f"Unexpected login hint: {message}"),
    )
    monkeypatch.setattr(streamer_dashboard, "st", fake_st)
    monkeypatch.setattr(
        streamer_dashboard,
        "_twitch_authorization_url",
        lambda: ("https://id.twitch.tv/oauth2/authorize?client_id=test&state=abc", None),
    )

    streamer_dashboard._render_twitch_login()

    assert len(rendered) == 1
    label, url, options = rendered[0]
    assert label == "🟣 Mit Twitch anmelden"
    assert url == "https://id.twitch.tv/oauth2/authorize?client_id=test&state=abc"
    assert options["type"] == "primary"
    assert options["use_container_width"] is True



def test_profile_slug_reservation_cannot_be_claimed_by_another_account(memory_db):
    assert creator_profile._claim_slug_reservation("creator-name", "12345")
    assert not creator_profile._claim_slug_reservation("creator-name", "99999")
    assert memory_db.reference("creator_profile_slugs/creator-name").get() == "12345"
    assert not creator_profile._release_slug_reservation("creator-name", "99999")
    assert memory_db.reference("creator_profile_slugs/creator-name").get() == "12345"
    assert creator_profile._release_slug_reservation("creator-name", "12345")
    assert memory_db.reference("creator_profile_slugs/creator-name").get() is None



def test_poll_vote_and_close_are_atomic_and_owner_scoped(memory_db):
    memory_db.reference("community_polls/poll_abc").set({
        "created_by": "12345", "options": ["A", "B"], "closed": False, "votes": {},
    })
    assert feedback_hub._cast_poll_vote("poll_abc", "99999", "B") == 1
    assert memory_db.reference("community_polls/poll_abc/votes/99999").get() == 1
    assert not feedback_hub._close_owned_poll("poll_abc", "99999")
    assert feedback_hub._close_owned_poll("poll_abc", "12345")
    with pytest.raises(ValueError, match="geschlossen"):
        feedback_hub._cast_poll_vote("poll_abc", "88888", "A")


def test_wishlist_mutations_recheck_owner(memory_db):
    memory_db.reference("streamdex_community_wishlist/wish123").set({
        "author_tid": "12345", "title": "Owned", "status": "Neu",
    })
    assert not streamdex_suite._set_owned_wishlist_status("wish123", "99999", "Erledigt")
    assert not streamdex_suite._delete_owned_wishlist_item("wish123", "99999")
    assert memory_db.reference("streamdex_community_wishlist/wish123/status").get() == "Neu"
    assert streamdex_suite._set_owned_wishlist_status("wish123", "12345", "Umgesetzt")
    assert streamdex_suite._delete_owned_wishlist_item("wish123", "12345")
    assert memory_db.reference("streamdex_community_wishlist/wish123").get() is None


def test_quiz_room_code_collision_never_overwrites_existing_room(monkeypatch, memory_db):
    memory_db.reference("streamdex_quiz_rooms/ABC123").set({
        "code": "ABC123", "created_by": "99999", "title": "Existing",
    })
    candidates = iter(["ABC123", "DEF456"])
    monkeypatch.setattr(streamdex_suite.secrets, "token_hex", lambda size: next(candidates))
    code = streamdex_suite._create_quiz_room(
        "12345", "TestCreator", "New room", [{"question": "Q", "options": ["A", "B"], "correct_index": 0}]
    )
    assert code == "DEF456"
    assert memory_db.reference("streamdex_quiz_rooms/ABC123/title").get() == "Existing"
    assert memory_db.reference("streamdex_quiz_rooms/DEF456/created_by").get() == "12345"


def test_quiz_answers_and_room_management_are_account_scoped(memory_db):
    memory_db.reference("streamdex_quiz_rooms/ABC123").set({
        "code": "ABC123", "created_by": "12345", "status": "open",
        "questions": [{"question": "Q", "options": ["A", "B"], "correct_index": 0}],
        "answers": {},
    })
    assert not streamdex_suite._manage_owned_quiz("ABC123", "99999", "close")
    with pytest.raises(ValueError, match="ungültig"):
        streamdex_suite._save_quiz_answer("ABC123", "../99999", 0, "A")
    assert streamdex_suite._save_quiz_answer("ABC123", "99999", 0, "B")
    assert memory_db.reference("streamdex_quiz_rooms/ABC123/answers/99999/0/choice").get() == 1
    with pytest.raises(ValueError, match="bereits beantwortet"):
        streamdex_suite._save_quiz_answer("ABC123", "99999", 0, "A")
    assert streamdex_suite._manage_owned_quiz("ABC123", "12345", "close")
    assert memory_db.reference("streamdex_quiz_rooms/ABC123/status").get() == "closed"
    with pytest.raises(ValueError, match="geschlossen"):
        streamdex_suite._save_quiz_answer("ABC123", "88888", 0, "A")




def test_paypal_checkout_creates_branded_order_and_saves_approval_url(monkeypatch, memory_db):
    fake_st = SimpleNamespace(secrets={
        "paypal": {
            "client_id": "sandbox-client",
            "client_secret": "sandbox-secret",
            "mode": "sandbox",
            "brand_name": "StreamDex",
        }
    })
    monkeypatch.setattr(shop, "st", fake_st)
    memory_db.reference("shop/orders/SDX-ABC234").set({
        "tid": "12345",
        "name": "testcreator",
        "status": "pending",
        "item_name": "Slot Machine",
        "price": "2.99",
        "games": ["slot"],
        "ts": int(time.time() * 1000),
    })
    requests_seen = []

    def fake_request(config, method, path, payload=None):
        requests_seen.append((config, method, path, payload))
        return {
            "id": "PAYPALORDER123",
            "links": [{"rel": "payer-action", "href": "https://www.sandbox.paypal.com/checkoutnow?token=PAYPALORDER123"}],
        }

    monkeypatch.setattr(shop, "_paypal_api_request", fake_request)

    url = shop.create_paypal_checkout("SDX-ABC234")

    assert url == "https://www.sandbox.paypal.com/checkoutnow?token=PAYPALORDER123"
    config, method, path, payload = requests_seen[0]
    assert config["mode"] == "sandbox"
    assert method == "POST"
    assert path == "/v2/checkout/orders"
    assert payload["purchase_units"][0]["amount"] == {"currency_code": "EUR", "value": "2.99"}
    assert payload["purchase_units"][0]["custom_id"] == "SDX-ABC234"
    assert payload["payment_source"]["paypal"]["experience_context"]["brand_name"] == "StreamDex"
    assert payload["payment_source"]["paypal"]["experience_context"]["return_url"].startswith(
        "https://streamdex.streamlit.app/?"
    )
    saved = memory_db.reference("shop/orders/SDX-ABC234").get()
    assert saved["paypal_order_id"] == "PAYPALORDER123"
    assert saved["paypal_approval_url"] == url
    assert saved["payment_provider"] == "paypal"


def test_paypal_return_verifies_amount_and_fulfills_once(monkeypatch, memory_db):
    monkeypatch.setattr(shop, "_paypal_config", lambda: {
        "mode": "sandbox", "base_url": "https://api-m.sandbox.paypal.com",
        "client_id": "test", "client_secret": "secret", "brand_name": "StreamDex",
    })
    memory_db.reference("shop/orders/SDX-ABC234").set({
        "tid": "12345",
        "name": "testcreator",
        "status": "pending",
        "item_name": "Slot Machine",
        "price": "2.99",
        "games": ["slot"],
        "payment_provider": "paypal",
        "paypal_order_id": "PAYPALORDER123",
    })
    calls = []

    def fake_request(config, method, path, payload=None):
        calls.append((method, path))
        return {
            "id": "PAYPALORDER123",
            "status": "COMPLETED",
            "purchase_units": [{
                "custom_id": "SDX-ABC234",
                "payments": {"captures": [{
                    "id": "CAPTUREABC123",
                    "status": "COMPLETED",
                    "amount": {"currency_code": "EUR", "value": "2.99"},
                }]},
            }],
        }

    monkeypatch.setattr(shop, "_paypal_api_request", fake_request)
    ok, message = shop.handle_paypal_return("PAYPALORDER123", "PAYER123")

    assert ok is True
    assert "freigeschaltet" in message
    assert memory_db.reference("shop/orders/SDX-ABC234/status").get() == "paid"
    assert memory_db.reference("game_flags/streamers/12345/slot").get() is True
    assert memory_db.reference("shop/orders/SDX-ABC234/payment_provider").get() == "paypal"
    assert memory_db.reference("shop/used_paypal_captures/CAPTUREABC123/order").get() == "SDX-ABC234"

    # The same return callback cannot grant the same order a second time or recapture it.
    again, _ = shop.handle_paypal_return("PAYPALORDER123", "PAYER123")
    assert again is True
    assert len(calls) == 1


def test_paypal_return_rejects_wrong_amount_without_fulfilment(monkeypatch, memory_db):
    monkeypatch.setattr(shop, "_paypal_config", lambda: {
        "mode": "sandbox", "base_url": "https://api-m.sandbox.paypal.com",
        "client_id": "test", "client_secret": "secret", "brand_name": "StreamDex",
    })
    memory_db.reference("shop/orders/SDX-ABC234").set({
        "tid": "12345", "name": "testcreator", "status": "pending",
        "item_name": "Slot Machine", "price": "2.99", "games": ["slot"],
        "payment_provider": "paypal", "paypal_order_id": "PAYPALORDER123",
    })
    monkeypatch.setattr(shop, "_paypal_api_request", lambda *a, **k: {
        "status": "COMPLETED",
        "purchase_units": [{
            "custom_id": "SDX-ABC234",
            "payments": {"captures": [{
                "id": "CAPTUREABC123", "status": "COMPLETED",
                "amount": {"currency_code": "EUR", "value": "0.01"},
            }]},
        }],
    })

    ok, message = shop.handle_paypal_return("PAYPALORDER123")

    assert ok is False
    assert "Betrag" in message
    assert memory_db.reference("shop/orders/SDX-ABC234/status").get() == "pending"
    assert memory_db.reference("game_flags/streamers/12345/slot").get() is None


def test_event_registration_prevents_duplicate_authenticated_account(memory_db):
    memory_db.reference("streamdex_events/event_123").set({
        "owner_tid": "12345", "title": "Community", "status": "open", "capacity": 3, "participants": {},
    })
    events._register_event_participant("event_123", "FirstName", "Twitch", "11111")
    with pytest.raises(ValueError, match="StreamDex-Konto"):
        events._register_event_participant("event_123", "ChangedName", "Discord", "11111")
    participants = memory_db.reference("streamdex_events/event_123/participants").get()
    assert len(participants) == 1
    assert next(iter(participants.values()))["registrant_tid"] == "11111"

    events._register_event_participant("event_123", "SecondName", "Web", "22222")
    assert len(memory_db.reference("streamdex_events/event_123/participants").get()) == 2


def test_event_registration_still_supports_anonymous_visitors(memory_db):
    memory_db.reference("streamdex_events/event_123").set({
        "owner_tid": "12345", "title": "Community", "status": "open", "capacity": 0, "participants": {},
    })
    events._register_event_participant("event_123", "Guest A", "Web", "")
    events._register_event_participant("event_123", "Guest B", "Web", "")
    assert len(memory_db.reference("streamdex_events/event_123/participants").get()) == 2

def test_tebex_checkout_creates_basket_and_saves_url(monkeypatch, memory_db):
    monkeypatch.setattr(shop, "st", SimpleNamespace(secrets={
        "tebex": {"account_token": "test-token-1234567890", "packages": {"slot": "12345"}}
    }))
    memory_db.reference("shop/orders/SDX-ABC234").set({
        "tid": "12345",
        "name": "testcreator",
        "status": "pending",
        "item_name": "Slot Machine",
        "items": ["slot"],
        "price": "2.99",
        "gross": "2.99",
        "games": ["slot"],
        "ts": int(time.time() * 1000),
    })
    calls = []

    def fake_request(config, method, path, payload=None):
        calls.append((method, path, payload))
        if method == "POST" and path.endswith("/baskets"):
            return {"data": {"ident": "basket-ident-123456"}}
        if method == "GET" and path.endswith("/basket-ident-123456"):
            return {"data": {
                "ident": "basket-ident-123456",
                "currency": "EUR",
                "base_price": 2.99,
                "links": {"checkout": "https://checkout.tebex.io/checkout/basket-ident-123456"},
            }}
        return {"data": {}}

    monkeypatch.setattr(shop, "_tebex_api_request", fake_request)
    url = shop.create_tebex_checkout("SDX-ABC234")

    assert url == "https://checkout.tebex.io/checkout/basket-ident-123456"
    assert ("POST", "baskets/basket-ident-123456/packages", {"package_id": "12345", "quantity": 1}) in calls
    saved = memory_db.reference("shop/orders/SDX-ABC234").get()
    assert saved["payment_provider"] == "tebex"
    assert saved["tebex_basket_ident"] == "basket-ident-123456"
    assert saved["tebex_checkout_url"] == url


def test_tebex_return_verifies_completed_basket_and_fulfils_once(monkeypatch, memory_db):
    monkeypatch.setattr(shop, "_tebex_config", lambda: {
        "account_token": "test-token-1234567890", "packages": {"slot": "12345"}
    })
    memory_db.reference("shop/orders/SDX-ABC234").set({
        "tid": "12345",
        "name": "testcreator",
        "status": "pending",
        "item_name": "Slot Machine",
        "price": "2.99",
        "games": ["slot"],
        "payment_provider": "tebex",
        "tebex_basket_ident": "basket-ident-123456",
    })
    calls = []

    def fake_request(config, method, path, payload=None):
        calls.append((method, path))
        return {"data": {
            "ident": "basket-ident-123456",
            "complete": True,
            "custom": {"streamdex_order": "SDX-ABC234"},
            "currency": "EUR",
            "base_price": 2.99,
        }}

    monkeypatch.setattr(shop, "_tebex_api_request", fake_request)
    ok, message = shop.handle_tebex_return("SDX-ABC234")

    assert ok is True
    assert "freigeschaltet" in message
    assert memory_db.reference("shop/orders/SDX-ABC234/status").get() == "paid"
    assert memory_db.reference("game_flags/streamers/12345/slot").get() is True
    assert memory_db.reference("shop/orders/SDX-ABC234/tip_id").get() == "tebex:basket-ident-123456"

    # Repeated returns do not call Tebex again or repeat fulfilment.
    again, _ = shop.handle_tebex_return("SDX-ABC234")
    assert again is True
    assert len(calls) == 1


def test_tebex_return_rejects_incomplete_or_wrong_price_basket(monkeypatch, memory_db):
    monkeypatch.setattr(shop, "_tebex_config", lambda: {
        "account_token": "test-token-1234567890", "packages": {"slot": "12345"}
    })
    memory_db.reference("shop/orders/SDX-ABC234").set({
        "tid": "12345", "name": "testcreator", "status": "pending",
        "item_name": "Slot Machine", "price": "2.99", "games": ["slot"],
        "payment_provider": "tebex", "tebex_basket_ident": "basket-ident-123456",
    })
    monkeypatch.setattr(shop, "_tebex_api_request", lambda *a, **k: {"data": {
        "ident": "basket-ident-123456",
        "complete": True,
        "custom": {"streamdex_order": "SDX-ABC234"},
        "currency": "EUR",
        "base_price": 0.01,
    }})

    ok, message = shop.handle_tebex_return("SDX-ABC234")

    assert ok is False
    assert "Betrag" in message
    assert memory_db.reference("shop/orders/SDX-ABC234/status").get() == "pending"
    assert memory_db.reference("game_flags/streamers/12345/slot").get() is None

