"""Dependency-free security regression tests for StreamDex account isolation."""
import unittest

from streamdex_security import (
    ACCOUNT_DELETE_PATHS,
    ACCOUNT_KEEP_PATHS,
    ADMIN_SESSION_MAX_AGE_SECONDS,
    USER_SESSION_MAX_AGE_SECONDS,
    account_path,
    has_active_admin_session,
    has_active_user_session,
    is_valid_twitch_id,
)


class TwitchIdTests(unittest.TestCase):
    def test_only_numeric_ids_are_valid(self):
        self.assertTrue(is_valid_twitch_id("123456"))
        self.assertTrue(is_valid_twitch_id(123456))
        for value in ("", "0/other", "../123", "12-34", "123?x=1", None, [], "-123"):
            with self.subTest(value=value):
                self.assertFalse(is_valid_twitch_id(value))

    def test_account_path_rejects_path_injection(self):
        self.assertEqual(account_path("stats/{t}", "123456"), "stats/123456")
        for value in ("../admin", "123/other", "123?x=1", None):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    account_path("stats/{t}", value)

    def test_account_paths_cover_new_private_tools_and_presence_is_last(self):
        self.assertEqual(ACCOUNT_DELETE_PATHS[-1], "presence/{t}")
        required = {
            "radar_watchlists/{t}",
            "streamdex_ideas/{t}",
            "streamdex_brackets/{t}",
            "streamdex_wheel/{t}",
            "streamdex_goals/{t}",
            "streamdex_modlog/{t}",
            "streamdex_modteam/{t}",
            "streamdex_planner/{t}",
            "streamdex_clips/{t}",
            "streamdex_web_auth/{t}",
            "streamdex_tool_usage/{t}",
            "beta_seen/{t}",
        }
        self.assertTrue(required.issubset(set(ACCOUNT_DELETE_PATHS)))
        self.assertTrue(set(ACCOUNT_KEEP_PATHS).isdisjoint(set(ACCOUNT_DELETE_PATHS)))


class UserSessionTests(unittest.TestCase):
    def setUp(self):
        self.session = {
            "authenticated_tid": "123456",
            "authenticated_at": 1000.0,
            "auth_method": "twitch",
        }

    def test_owner_with_live_twitch_session_is_allowed(self):
        self.assertTrue(has_active_user_session(self.session, "123456", now=1001))

    def test_owner_with_live_desktop_session_is_allowed(self):
        self.session["auth_method"] = "desktop"
        self.assertTrue(has_active_user_session(self.session, "123456", now=1001))

    def test_different_account_cannot_access_session(self):
        self.assertFalse(has_active_user_session(self.session, "999999", now=1001))

    def test_invalid_id_and_unknown_auth_method_are_rejected(self):
        self.assertFalse(has_active_user_session(self.session, "../123", now=1001))
        self.session["auth_method"] = "admin"
        self.assertFalse(has_active_user_session(self.session, "123456", now=1001))

    def test_session_expiry_and_future_timestamp_are_rejected(self):
        self.assertFalse(
            has_active_user_session(
                self.session,
                "123456",
                now=1000 + USER_SESSION_MAX_AGE_SECONDS + 1,
            )
        )
        self.assertFalse(has_active_user_session(self.session, "123456", now=999))

    def test_missing_timestamp_is_rejected(self):
        self.session.pop("authenticated_at")
        self.assertFalse(has_active_user_session(self.session, "123456", now=1001))


class AdminSessionTests(unittest.TestCase):
    def test_admin_session_requires_auth_and_expires(self):
        session = {"auth_ok": True, "admin_authenticated_at": 500.0}
        self.assertTrue(has_active_admin_session(session, now=501))
        self.assertFalse(
            has_active_admin_session(
                session,
                now=500 + ADMIN_SESSION_MAX_AGE_SECONDS + 1,
            )
        )
        self.assertFalse(has_active_admin_session({"admin_authenticated_at": 500.0}, now=501))

    def test_future_admin_timestamp_is_rejected(self):
        self.assertFalse(
            has_active_admin_session(
                {"auth_ok": True, "admin_authenticated_at": 501.0},
                now=500,
            )
        )


if __name__ == "__main__":
    unittest.main()
