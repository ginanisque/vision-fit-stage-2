"""Small psycopg boundary; application traffic uses Neon's pooled URL."""
from __future__ import annotations

from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from .settings import get_settings


@contextmanager
def connection():
    with psycopg.connect(get_settings().database_url, row_factory=dict_row, connect_timeout=5) as conn:
        yield conn


def database_health() -> bool:
    try:
        with connection() as conn:
            return conn.execute("select 1").fetchone() is not None
    except psycopg.Error:
        return False
