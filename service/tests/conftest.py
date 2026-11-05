"""Keep the backend test suite independent of the developer's local ``.env``.

``app.main`` reads ``VISIONFIT_CORS_ORIGINS`` once at import time to build its
CORS allow-list. A developer's local ``.env`` can override that value, which
would flip ``test_cors_allows_local_frontend_origin`` and, more generally, let
machine-local state change test results. Pinning the value here — before any
application module is imported — keeps the suite hermetic: ``load_dotenv``
never overrides an environment variable that is already set.
"""

import os

os.environ.setdefault(
    "VISIONFIT_CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174",
)
os.environ.setdefault("ROBOFLOW_ENABLED", "false")
os.environ.setdefault("VISIONFIT_RETENTION_ENABLED", "false")

# Safe placeholders keep unit tests hermetic; database and storage calls are mocked.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/visionfit_test")
os.environ.setdefault("NEON_AUTH_BASE_URL", "https://auth.example.test")
os.environ.setdefault("NEON_AUTH_JWKS_URL", "https://auth.example.test/.well-known/jwks.json")
os.environ.setdefault("AWS_ENDPOINT_URL_S3", "https://storage.example.test")
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("S3_BUCKET", "visionfit-test")
