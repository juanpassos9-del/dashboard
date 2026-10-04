import base64
import hashlib
import json

from cryptography.fernet import Fernet, InvalidToken


class InvalidAuthCookie(ValueError):
    pass


def _cipher(secret: str) -> Fernet:
    if not secret:
        raise ValueError("An auth cookie secret is required")
    digest = hashlib.sha256(f"terminal-tts-auth-cookie-v1:{secret}".encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_refresh_token(secret: str, refresh_token: str) -> str:
    if not refresh_token:
        raise ValueError("A refresh token is required")
    payload = json.dumps({"refresh_token": refresh_token, "version": 1}).encode("utf-8")
    return _cipher(secret).encrypt(payload).decode("ascii")


def decrypt_refresh_token(secret: str, encrypted_value: str, max_age: int) -> str:
    try:
        payload = json.loads(_cipher(secret).decrypt(encrypted_value.encode("ascii"), ttl=max_age))
    except (InvalidToken, ValueError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
        raise InvalidAuthCookie("The saved authentication cookie is invalid or expired") from exc
    refresh_token = payload.get("refresh_token") if isinstance(payload, dict) and payload.get("version") == 1 else None
    if not isinstance(refresh_token, str) or not refresh_token:
        raise InvalidAuthCookie("The saved authentication cookie has an invalid payload")
    return refresh_token
