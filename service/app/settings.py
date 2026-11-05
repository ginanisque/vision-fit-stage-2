"""Validated runtime settings loaded from the project-local environment."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class Settings:
    database_url: str
    neon_auth_base_url: str
    neon_auth_jwks_url: str
    s3_endpoint: str
    s3_region: str
    s3_bucket: str
    bootstrap_admin_emails: frozenset[str]


@lru_cache
def get_settings() -> Settings:
    admins = frozenset(
        email.strip().lower()
        for email in os.getenv("VISIONFIT_BOOTSTRAP_ADMIN_EMAILS", "").split(",")
        if email.strip()
    )
    return Settings(
        database_url=os.getenv("DATABASE_URL_POOLED", "").strip() or _required("DATABASE_URL"),
        neon_auth_base_url=_required("NEON_AUTH_BASE_URL").rstrip("/"),
        neon_auth_jwks_url=_required("NEON_AUTH_JWKS_URL"),
        s3_endpoint=_required("AWS_ENDPOINT_URL_S3").rstrip("/"),
        s3_region=os.getenv("S3_REGION", "").strip() or _required("AWS_REGION"),
        s3_bucket=_required("S3_BUCKET"),
        bootstrap_admin_emails=admins,
    )
