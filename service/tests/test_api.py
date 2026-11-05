"""API integration tests: the quality endpoint returns a recorded decision and
the decision log is append-only.
"""
from io import BytesIO
from uuid import uuid4

import cv2
import numpy as np
from fastapi.testclient import TestClient

from app.auth import SessionUser, current_user
from app.main import app

client = TestClient(app)


def _structured_image(mean: float = 128.0, amplitude: float = 60.0) -> np.ndarray:
    height, width = 300, 400
    yy, xx = np.mgrid[0:height, 0:width]
    rng = np.random.default_rng(0)
    image = mean + amplitude * np.sin(xx / 12.0) * np.sin(yy / 12.0) + rng.normal(0, 8, size=(height, width))
    return np.clip(image, 0, 255).astype(np.uint8)


def _png_bytes(image: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", image)
    assert ok
    return buf.tobytes()


def _quality_request(*, consent: bool = True, data: dict | None = None, files: dict | None = None):
    user = SessionUser(uuid4(), "test-subject", "customer@example.test", "customer")
    app.dependency_overrides[current_user] = lambda: user
    try:
        return client.post(
            "/api/quality",
            data={"view": "front", "consent": str(consent).lower(), **(data or {})},
            files=files or {"file": ("front.png", _png_bytes(_structured_image()), "image/png")},
        )
    finally:
        app.dependency_overrides.pop(current_user, None)


def test_health_reports_opencv_5(monkeypatch) -> None:
    monkeypatch.setattr("app.main.database_health", lambda: True)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["opencv"].startswith("5.")


def test_cors_allows_local_frontend_origin() -> None:
    response = client.options(
        "/api/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_health_does_not_expose_workflow_ids(monkeypatch) -> None:
    monkeypatch.setattr("app.main.roboflow_status", lambda: {
        "enabled": True, "configured": True, "ready": True,
        "keypointWorkflow": "secret-keypoint-workflow",
        "segmentationWorkflow": "secret-segmentation-workflow",
    })
    monkeypatch.setattr("app.main.database_health", lambda: True)
    response = client.get("/api/health")
    assert response.status_code == 200
    vision = response.json()["measurementVision"]
    assert vision["ready"] is True
    assert vision["measurementPathEnabled"] is False
    assert "validated against tape measurements" in vision["measurementPathReason"]
    assert "keypointWorkflow" not in vision
    assert "segmentationWorkflow" not in vision


def test_good_image_allows_proceed() -> None:
    response = _quality_request()
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "proceed"
    assert body["view"] == "front"
    assert body["imageFingerprint"]["sha256"]
    assert body["provisionalThresholds"] is True


def test_blurry_image_requests_recapture() -> None:
    blurred = cv2.GaussianBlur(_structured_image(), (0, 0), 12)
    response = _quality_request(
        data={"view": "side"},
        files={"file": ("side.png", _png_bytes(blurred), "image/png")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "recapture"
    assert any("blurry" in reason for reason in body["reasons"])


def test_dark_image_requests_recapture() -> None:
    dark = (_structured_image() * 0.07).astype(np.uint8)
    response = _quality_request(
        files={"file": ("front.png", _png_bytes(dark), "image/png")},
    )
    assert response.status_code == 200
    assert response.json()["decision"] == "recapture"


def test_invalid_view_rejected() -> None:
    response = _quality_request(
        data={"view": "back"},
        files={"file": ("back.png", _png_bytes(_structured_image()), "image/png")},
    )
    assert response.status_code == 400


def test_undecodable_file_rejected() -> None:
    response = _quality_request(
        files={"file": ("front.txt", b"not an image", "text/plain")},
    )
    assert response.status_code == 400


def test_quality_requires_authentication() -> None:
    response = client.post(
        "/api/quality",
        data={"view": "front", "consent": "true"},
        files={"file": ("front.png", _png_bytes(_structured_image()), "image/png")},
    )
    assert response.status_code == 401


def test_quality_requires_explicit_consent() -> None:
    assert _quality_request(consent=False).status_code == 403


def test_quality_upload_size_is_bounded(monkeypatch) -> None:
    monkeypatch.setattr("app.main.MAX_CAPTURE_BYTES", 8)
    response = _quality_request(files={"file": ("large.png", b"x" * 9, "image/png")})
    assert response.status_code == 413


def test_customer_can_delete_only_their_capture(monkeypatch) -> None:
    user = SessionUser(uuid4(), "test-subject", "customer@example.test", "customer")
    deleted = {}
    monkeypatch.setattr("app.main.delete_capture_session", lambda session_id, owner_id: (
        deleted.update({"session_id": session_id, "owner_id": owner_id})
        or {"assetsDeleted": 3, "measurementTablesDeleted": 1}
    ))
    app.dependency_overrides[current_user] = lambda: user
    try:
        response = client.delete("/api/capture-sessions/session-1")
    finally:
        app.dependency_overrides.pop(current_user, None)
    assert response.status_code == 200
    assert response.json()["deleted"] is True
    assert deleted == {"session_id": "session-1", "owner_id": user.id}


def test_persisted_decisions_require_admin() -> None:
    assert client.get("/api/decisions").status_code == 401


def test_training_export_requires_admin() -> None:
    user = SessionUser(uuid4(), "test-subject", "customer@example.test", "customer")
    app.dependency_overrides[current_user] = lambda: user
    try:
        response = client.get("/api/admin/training-export")
    finally:
        app.dependency_overrides.pop(current_user, None)
    assert response.status_code == 403


def test_admin_can_download_training_export(monkeypatch, tmp_path) -> None:
    from zipfile import ZIP_DEFLATED, ZipFile

    export_path = tmp_path / "training-export.zip"
    with ZipFile(export_path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("manifest.csv", "path,training_consent\n")
    monkeypatch.setattr(
        "app.main.create_training_export",
        lambda: (str(export_path), 1),
    )
    user = SessionUser(uuid4(), "test-admin", "admin@example.test", "admin")
    app.dependency_overrides[current_user] = lambda: user
    try:
        response = client.get("/api/admin/training-export")
    finally:
        app.dependency_overrides.pop(current_user, None)

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "attachment;" in response.headers["content-disposition"]
    assert response.headers["cache-control"] == "no-store"
    assert not export_path.exists()
