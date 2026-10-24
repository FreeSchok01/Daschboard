"""Regression tests for private R2 object-key validation."""
import unittest

from r2_storage import is_valid_r2_object_key


class R2ObjectKeyValidationTests(unittest.TestCase):
    def test_accepts_nested_relative_keys(self):
        self.assertTrue(is_valid_r2_object_key("games/my-game/v1.0.zip"))
        self.assertTrue(is_valid_r2_object_key("Spiele/Mein Spiel.zip"))

    def test_rejects_empty_and_non_string_values(self):
        for value in ("", "   ", None, 42):
            with self.subTest(value=value):
                self.assertFalse(is_valid_r2_object_key(value))

    def test_rejects_absolute_or_traversal_keys(self):
        for value in ("/game.zip", "../game.zip", "games/../game.zip", "games/./game.zip"):
            with self.subTest(value=value):
                self.assertFalse(is_valid_r2_object_key(value))

    def test_rejects_url_like_or_controlled_keys(self):
        for value in ("https://example.com/game.zip", "game.zip?x=1", "game#part.zip",
                      "games//game.zip", "games\\game.zip", "games/\nfile.zip"):
            with self.subTest(value=value):
                self.assertFalse(is_valid_r2_object_key(value))

    def test_rejects_overlong_keys(self):
        self.assertFalse(is_valid_r2_object_key("a" * 513))


if __name__ == "__main__":
    unittest.main()
