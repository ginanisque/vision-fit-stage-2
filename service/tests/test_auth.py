from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import HTTPException

from app import auth


def configured_issuer() -> str:
    auth_url = urlsplit(auth.get_settings().neon_auth_base_url)
    return f"{auth_url.scheme}://{auth_url.netloc}"


class SigningKey:
    def __init__(self, key):
        self.key = key


class JwksClient:
    def __init__(self, public_key):
        self.public_key = public_key

    def get_signing_key_from_jwt(self, _token):
        return SigningKey(self.public_key)


def token(private_key, issuer: str, expires: timedelta = timedelta(minutes=5)):
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": "neon-user-1", "email": "customer@example.test", "iss": issuer,
         "iat": now, "exp": now + expires},
        private_key, algorithm="EdDSA", headers={"kid": "test-key"},
    )


def test_verify_token_accepts_valid_eddsa_neon_issuer(monkeypatch):
    private_key = Ed25519PrivateKey.generate()
    issuer = configured_issuer()
    monkeypatch.setattr(auth, "_jwks_client", lambda: JwksClient(private_key.public_key()))
    claims = auth.verify_token(token(private_key, issuer))
    assert claims["sub"] == "neon-user-1"


def test_verify_token_rejects_expired_token(monkeypatch):
    private_key = Ed25519PrivateKey.generate()
    issuer = configured_issuer()
    monkeypatch.setattr(auth, "_jwks_client", lambda: JwksClient(private_key.public_key()))
    with pytest.raises(HTTPException) as rejected:
        auth.verify_token(token(private_key, issuer, timedelta(seconds=-1)))
    assert rejected.value.status_code == 401
