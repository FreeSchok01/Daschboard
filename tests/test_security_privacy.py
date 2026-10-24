import pytest

from privacy_security import (
    admin_session_is_valid,
    collect_user_shared_data,
    is_valid_twitch_id,
    make_signed_oauth_state,
    oauth_state_key,
    oauth_state_record_is_active,
    plan_shared_account_deletions,
    safe_exception_label,
    verify_signed_oauth_state,
)


def test_twitch_ids_are_numeric_and_path_safe():
    assert is_valid_twitch_id("123")
    assert is_valid_twitch_id(123)
    assert is_valid_twitch_id("123456789012345")
    for invalid in ("", "0/../456", "../123", "123/other", "-123", "123.4",
                    "1234567890123456", None, True):
        assert not is_valid_twitch_id(invalid)


def test_admin_session_age_and_clock_skew():
    assert admin_session_is_valid(950, now=1000, ttl_seconds=100)
    assert not admin_session_is_valid(800, now=1000, ttl_seconds=100)
    assert not admin_session_is_valid(1001, now=1000, ttl_seconds=100)
    assert not admin_session_is_valid("not-a-time", now=1000)
    assert not admin_session_is_valid(100, now=100, ttl_seconds=0)


def test_oauth_state_signature_and_expiry():
    state = make_signed_oauth_state("test-secret", now=10_000, nonce="abcdefgh_12345678")
    assert verify_signed_oauth_state(state, "test-secret", now=10_100, max_age_seconds=600)
    assert not verify_signed_oauth_state(state, "wrong-secret", now=10_100)
    parts = state.split(".")
    parts[-1] = ("0" if parts[-1][0] != "0" else "1") + parts[-1][1:]
    assert not verify_signed_oauth_state(".".join(parts), "test-secret", now=10_100)
    assert not verify_signed_oauth_state(state, "test-secret", now=10_601, max_age_seconds=600)
    assert not verify_signed_oauth_state("bad.state", "test-secret", now=10_100)
    assert oauth_state_key(state) != state


def test_oauth_state_record_must_be_pending_and_unexpired():
    record = {"issued_at_ms": 1_000, "expires_at_ms": 2_000, "consumed": False}
    assert oauth_state_record_is_active(record, now_ms=1_500)
    assert not oauth_state_record_is_active({**record, "consumed": True}, now_ms=1_500)
    assert not oauth_state_record_is_active(record, now_ms=2_001)
    assert not oauth_state_record_is_active({"issued_at_ms": "bad", "expires_at_ms": 2_000}, now_ms=1_500)
    assert not oauth_state_record_is_active(None, now_ms=1_500)


def _shared_data_fixture():
    return {
        "feedback_inbox": {
            "my-feedback": {"tid": "123", "title": "My idea", "votes": {"123": True}},
            "peer-feedback": {"tid": "456", "title": "Peer idea", "votes": {"123": True, "456": True}},
        },
        "streamdex_community_wishlist": {
            "my-wish": {"author_tid": "123", "title": "My wish", "votes": {"456": True}},
            "peer-wish": {"author_tid": "456", "title": "Peer wish", "votes": {"123": True, "456": True}},
        },
        "community_polls": {
            "my-poll": {"created_by": "123", "question": "My poll", "options": ["A", "B"],
                        "votes": {"123": 1, "456": 0}, "closed": False},
            "peer-poll": {"created_by": "456", "question": "Peer poll", "options": ["X", "Y"],
                          "votes": {"123": 1, "456": 0}, "closed": False},
        },
        "streamdex_quiz_rooms": {
            "ABC123": {"created_by": "123", "title": "Mine", "questions": [{"question": "Q"}],
                       "answers": {"456": {"0": {"choice": 0}}, "789": {"0": {"choice": 1}}}},
            "DEF456": {"created_by": "456", "title": "Peer room",
                       "answers": {"123": {"0": {"choice": 1}}, "456": {"0": {"choice": 0}}}},
        },
        "streamdex_events": {
            "eventMine": {"owner_tid": "123", "title": "My event",
                          "participants": {"p1": {"display_name": "Other"}}},
            "eventPeer": {"owner_tid": "456", "title": "Peer event",
                          "participants": {"p123": {"display_name": "Me", "registrant_tid": "123"},
                                          "p456": {"display_name": "Peer", "registrant_tid": "456"}}},
        },
    }


def test_shared_export_includes_only_current_users_contributions():
    data = collect_user_shared_data("123", _shared_data_fixture())

    assert set(data["feedback"]["submitted"]) == {"my-feedback"}
    assert data["feedback"]["submitted"]["my-feedback"]["vote_count"] == 1
    assert "votes" not in data["feedback"]["submitted"]["my-feedback"]
    assert data["feedback"]["votes"]["peer-feedback"]["vote"] is True
    assert set(data["wishlist"]["created"]) == {"my-wish"}
    assert set(data["wishlist"]["votes"]) == {"peer-wish"}
    assert data["polls"]["votes"]["peer-poll"]["selected_option"] == "Y"
    assert "456" not in str(data["polls"]["created"]["my-poll"])
    assert set(data["quizzes"]["created"]) == {"ABC123"}
    assert "answers" not in data["quizzes"]["created"]["ABC123"]
    assert set(data["quizzes"]["your_answers"]) == {"DEF456"}
    assert "456" not in str(data["quizzes"]["your_answers"])
    assert set(data["events"]["created"]) == {"eventMine"}
    assert "Other" not in str(data["events"]["created"]["eventMine"])
    assert set(data["events"]["your_registrations"]) == {"eventPeer"}


def test_shared_deletion_plan_removes_only_owned_records_and_user_contributions():
    roots = _shared_data_fixture()
    paths = set(plan_shared_account_deletions("123", roots))

    assert "feedback_inbox/my-feedback" in paths
    assert "feedback_inbox/peer-feedback/votes/123" in paths
    assert "streamdex_community_wishlist/my-wish" in paths
    assert "streamdex_community_wishlist/peer-wish/votes/123" in paths
    assert "community_polls/my-poll" in paths
    assert "community_polls/peer-poll/votes/123" in paths
    assert "streamdex_quiz_rooms/ABC123" in paths
    assert "streamdex_quiz_rooms/DEF456/answers/123" in paths
    assert "streamdex_events/eventMine" in paths
    assert "streamdex_events/eventPeer/participants/p123" in paths
    assert "feedback_inbox/peer-feedback" not in paths
    assert "community_polls/peer-poll" not in paths
    assert "streamdex_quiz_rooms/DEF456" not in paths
    assert "streamdex_quiz_rooms/DEF456/answers/456" not in paths
    assert "streamdex_events/eventPeer" not in paths
    assert "streamdex_events/eventPeer/participants/p456" not in paths


@pytest.mark.parametrize("tid", ["", "123/456", "../123", "abc"])
def test_shared_account_operations_reject_invalid_user_ids(tid):
    with pytest.raises(ValueError):
        collect_user_shared_data(tid, {})
    with pytest.raises(ValueError):
        plan_shared_account_deletions(tid, {})


def test_exception_label_does_not_disclose_secret_bearing_message():
    exc = RuntimeError("failed while handling access_token=super-secret")
    assert safe_exception_label(exc) == "RuntimeError"
    assert "super-secret" not in safe_exception_label(exc)
