import unittest

from execution.auth_cookie import (
    InvalidAuthCookie,
    decrypt_refresh_token,
    encrypt_refresh_token,
    read_browser_cookie,
)


class AuthCookieTests(unittest.TestCase):
    def test_reads_fresh_browser_cookie_snapshot(self):
        class Manager:
            def get(self, _name=None):
                return None

            def get_all(self):
                return {"tts_auth_refresh_v1": "fresh-cookie"}

        self.assertEqual(read_browser_cookie(Manager(), "tts_auth_refresh_v1"), "fresh-cookie")

    def test_uses_constructor_snapshot_on_initial_component_render(self):
        class Manager:
            def get(self, name):
                return {"tts_auth_refresh_v1": "initial-cookie"}.get(name)

            def get_all(self):
                raise AssertionError("initial render must not mount the component twice")

        self.assertEqual(
            read_browser_cookie(Manager(), "tts_auth_refresh_v1", initial_read=True),
            "initial-cookie",
        )

    def test_round_trip(self):
        token = encrypt_refresh_token("test-secret", "refresh-token")
        self.assertEqual(decrypt_refresh_token("test-secret", token, 3600), "refresh-token")

    def test_rejects_wrong_secret(self):
        token = encrypt_refresh_token("test-secret", "refresh-token")
        with self.assertRaises(InvalidAuthCookie):
            decrypt_refresh_token("different-secret", token, 3600)

    def test_rejects_expired_cookie(self):
        expired = encrypt_refresh_token("test-secret", "refresh-token")
        with self.assertRaises(InvalidAuthCookie):
            decrypt_refresh_token("test-secret", expired, -1)

    def test_rejects_empty_secret_or_token(self):
        with self.assertRaises(ValueError):
            encrypt_refresh_token("", "refresh-token")
        with self.assertRaises(ValueError):
            encrypt_refresh_token("test-secret", "")


if __name__ == "__main__":
    unittest.main()
