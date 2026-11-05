"""Neon Auth bearer-token verification and application-role resolution."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException

from .database import connection
from .settings import get_settings

Role = Literal["admin", "customer"]


@dataclass(frozen=True)
class SessionUser:
    id: UUID
    auth_subject: str
    email: str
    role: Role


@lru_cache
def _jwks_client() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(get_settings().neon_auth_jwks_url, cache_jwk_set=True, lifespan=300)


def _bearer_token(authorization: str | None) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "Sign in required", headers={"WWW-Authenticate": "Bearer"})
    return token


def verify_token(token: str) -> dict:
    try:
        auth_url = urlsplit(get_settings().neon_auth_base_url)
        issuer = f"{auth_url.scheme}://{auth_url.netloc}"
        signing_key = _jwks_client().get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["EdDSA"],
            issuer=issuer,
            options={"verify_aud": False, "require": ["exp", "iat", "sub", "iss"]},
        )
    except jwt.PyJWTError as error:
        raise HTTPException(401, "Session token is invalid or expired") from error
    except Exception as error:
        raise HTTPException(503, "Authentication keys are temporarily unavailable") from error


def _resolve_user(claims: dict) -> SessionUser:
    subject = str(claims["sub"])
    email = str(claims.get("email", "")).strip().lower()
    if not email:
        raise HTTPException(401, "Authenticated account has no email address")
    name = str(claims.get("name", "")).strip() or None
    bootstrap_role: Role = "admin" if email in get_settings().bootstrap_admin_emails else "customer"
    with connection() as conn:
        row = conn.execute(
            """
            insert into app_users (email, display_name, role, auth_provider, auth_subject)
            values (%s, %s, %s, 'neon_auth', %s)
            on conflict (auth_provider, auth_subject)
              where auth_provider is not null and auth_subject is not null
            do update set email = excluded.email,
                          display_name = coalesce(excluded.display_name, app_users.display_name),
                          role = case when excluded.role = 'admin' then 'admin'::app_role else app_users.role end,
                          active = true
            returning id, auth_subject, email, role::text
            """,
            (email, name, bootstrap_role, subject),
        ).fetchone()
    return SessionUser(id=row["id"], auth_subject=row["auth_subject"], email=row["email"], role=row["role"])


def current_user(authorization: str | None = Header(default=None)) -> SessionUser:
    return _resolve_user(verify_token(_bearer_token(authorization)))


def require_admin(user: SessionUser = Depends(current_user)) -> SessionUser:
    if user.role != "admin":
        raise HTTPException(403, "Administrator access required")
    return user


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/me")
async def me(user: SessionUser = Depends(current_user)) -> dict:
    return {"id": str(user.id), "email": user.email, "role": user.role}
