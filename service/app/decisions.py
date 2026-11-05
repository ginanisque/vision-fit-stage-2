"""Decision records: turn a quality result into a recorded recapture/proceed decision.

Every decision carries provenance (image fingerprint, dimensions, metrics, the
exact thresholds used, and a timestamp) so the outcome is auditable. Thresholds
are flagged as provisional.
"""
from __future__ import annotations

import hashlib
import threading
import uuid
from datetime import datetime, timezone

import numpy as np

from .config import DEFAULT_THRESHOLDS, QualityThresholds
from .quality import evaluate_quality

QUALITY_SCOPE = (
    "Exposure and blur only. Posture, framing, waist-cord placement and "
    "measurement suitability are NOT verified by this check."
)


def _image_fingerprint(image_bytes: bytes) -> dict:
    return {"sha256": hashlib.sha256(image_bytes).hexdigest()}


def build_decision(
    view: str,
    image: np.ndarray,
    image_bytes: bytes,
    thresholds: QualityThresholds = DEFAULT_THRESHOLDS,
    checked_at: datetime | None = None,
) -> dict:
    result = evaluate_quality(image, thresholds, view)
    decision = "recapture" if not result.passed else "proceed"
    checked_at = checked_at or datetime.now(timezone.utc)

    return {
        "id": str(uuid.uuid4()),
        "decision": decision,
        "view": view,
        "imageFingerprint": _image_fingerprint(image_bytes),
        "dimensions": {"width": int(image.shape[1]), "height": int(image.shape[0])},
        "checks": {
            "exposure": {
                "status": result.exposure.status,
                "lumaMean": round(result.exposure.luma_mean, 2),
                "darkClipFraction": round(result.exposure.dark_clip_fraction, 6),
                "brightClipFraction": round(result.exposure.bright_clip_fraction, 6),
            },
            "blur": {
                "status": result.blur.status,
                "laplacianVariance": round(result.blur.laplacian_variance, 2),
            },
        },
        "reasons": list(result.reasons),
        "thresholds": thresholds.as_dict(),
        "provisionalThresholds": True,
        "scope": QUALITY_SCOPE,
        "checkedAt": checked_at.isoformat(),
    }


class DecisionLog:
    """In-memory, thread-safe decision log. Persistence is deferred to a later milestone."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: list[dict] = []

    def append(self, record: dict) -> dict:
        with self._lock:
            self._records.append(record)
        return record

    def list(self, limit: int | None = None) -> list[dict]:
        with self._lock:
            items = list(self._records)
        return items[-limit:] if limit else items
