import unittest

from execution.auth_cookie import InvalidAuthCookie, decrypt_refresh_token, encrypt_refresh_token


class AuthCookieTests(unittest.TestCase):
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
