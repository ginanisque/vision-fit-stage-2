"""VisionFit OpenCV service with Neon persistence, Auth, and private storage."""
from __future__ import annotations

import asyncio
import cv2
import logging
import numpy as np
import os
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from .config import DEFAULT_THRESHOLDS
from .decisions import DecisionLog, build_decision
from .posture import estimate_pose, load_pose, view_orientation
from .auth import SessionUser, current_user, require_admin, router as auth_router
from .capture_store import (
    admin_capture_session, admin_capture_sessions, create_training_export,
    delete_capture_session, ensure_session,
    persist_analysis, purge_expired_capture_sessions, recent_decisions,
)
from .database import database_health
from .measurements import (
    persist_video_estimates, router as measurements_router,
)
from .roboflow import configuration_status as roboflow_status
from .circumference import (
    _apply_profile, _load_calibration_profile, estimate_back_measurements,
    estimate_circumferences,
)
from .path_estimation import reference_scale_mm_per_pixel, view_scale_mm_per_pixel

logger = logging.getLogger(__name__)


def _retention_days() -> int:
    value = os.getenv("VISIONFIT_RETENTION_DAYS", "30")
    try:
        days = int(value)
    except ValueError as error:
        raise RuntimeError("VISIONFIT_RETENTION_DAYS must be a positive integer") from error
    if days < 1:
        raise RuntimeError("VISIONFIT_RETENTION_DAYS must be a positive integer")
    return days


def _retention_enabled() -> bool:
    value = os.getenv("VISIONFIT_RETENTION_ENABLED", "true").strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError("VISIONFIT_RETENTION_ENABLED must be a boolean")


async def _retention_worker() -> None:
    while True:
        try:
            await asyncio.to_thread(purge_expired_capture_sessions, _retention_days())
        except Exception:
            logger.exception("VisionFit capture-retention cleanup failed")
        await asyncio.sleep(60 * 60)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if not _retention_enabled():
        yield
        return
    _retention_days()
    task = asyncio.create_task(_retention_worker())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="VisionFit quality service", version="0.1.0", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(measurements_router)


@app.get("/")
def root() -> dict:
    return {
        "service": "Ginani VisionFit API",
        "status": "ok",
        "docs": "/docs",
        "health": "/api/health",
        "measurementDefinitions": "/api/measurements/definitions",
    }


def _cors_origins() -> list[str]:
    """Only allow browser origins explicitly configured for this deployment."""
    value = os.getenv(
        "VISIONFIT_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:5174,http://127.0.0.1:5174",
    )
    return [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]

# Local development convenience: the Vite frontend proxies /api to this service,
# so CORS is a fallback only.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)

log = DecisionLog()

QUALITY_VIEWS = {"front", "side"}
CAPTURE_VIEWS = {"front", "side", "back"}
MIN_DIMENSION = 64


@app.get("/api/health")
def health() -> dict:
    # Keep Roboflow workflow identifiers out of the unauthenticated health check.
    vision = {
        key: value for key, value in roboflow_status().items()
        if key not in ("keypointWorkflow", "segmentationWorkflow")
    }
    vision["measurementPathEnabled"] = False
    vision["measurementPathReason"] = (
        "Roboflow tailoring-point paths remain disabled until their labels are validated against tape measurements."
    )
    return {"status": "ok", "opencv": cv2.__version__, "database": "ok" if database_health() else "unavailable",
            "measurementVision": vision}


@app.post("/api/quality")
async def quality(
    view: str = Form(...), consent: bool = Form(False), file: UploadFile = File(...),
    _user: SessionUser = Depends(current_user),
) -> dict:
    if not consent:
        raise HTTPException(status_code=403, detail="Explicit consent is required before processing")
    if view not in QUALITY_VIEWS:
        raise HTTPException(status_code=400, detail="view must be 'front' or 'side'")

    data = await file.read(MAX_CAPTURE_BYTES + 1)
    if len(data) > MAX_CAPTURE_BYTES:
        raise HTTPException(status_code=413, detail="Image exceeds 20 MiB")
    if not data:
        raise HTTPException(status_code=400, detail="empty file")

    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=400, detail="could not decode image")

    if image.shape[0] < MIN_DIMENSION or image.shape[1] < MIN_DIMENSION:
        raise HTTPException(status_code=400, detail="image too small to evaluate")

    record = build_decision(view, image, data, DEFAULT_THRESHOLDS)
    log.append(record)
    return record


@app.get("/api/decisions")
def decisions(limit: int = 20, _admin: SessionUser = Depends(require_admin)) -> dict:
    return {"records": recent_decisions(limit)}


@app.get("/api/admin/capture-sessions")
def capture_sessions(limit: int = 100, _admin: SessionUser = Depends(require_admin)) -> dict:
    return {"sessions": admin_capture_sessions(limit)}


@app.get("/api/admin/capture-sessions/{session_id}")
def capture_session_detail(session_id: str, _admin: SessionUser = Depends(require_admin)) -> dict:
    detail = admin_capture_session(session_id)
    if detail is None:
        raise HTTPException(404, "Capture session not found")
    return detail


@app.get("/api/admin/training-export")
def training_export(_admin: SessionUser = Depends(require_admin)) -> FileResponse:
    export_path, image_count = create_training_export()
    if image_count == 0:
        os.unlink(export_path)
        raise HTTPException(404, "No training-consented capture images are available to export")
    filename = f"visionfit-training-consented-{datetime.now(timezone.utc):%Y%m%d}.zip"
    return FileResponse(
        export_path,
        media_type="application/zip",
        filename=filename,
        headers={"Cache-Control": "no-store"},
        background=BackgroundTask(os.unlink, export_path),
    )


@app.delete("/api/capture-sessions/{session_id}")
def delete_own_capture_session(session_id: str, user: SessionUser = Depends(current_user)) -> dict:
    deleted = delete_capture_session(session_id, owner_id=user.id)
    if deleted is None:
        raise HTTPException(404, "Capture session not found")
    return {"deleted": True, **deleted}


# VF-2 uses its own endpoint so VF-0's narrower contract remains compatible.
from .capture import capture_decision

MAX_CAPTURE_BYTES = 20 * 1024 * 1024


@app.post('/api/measurement-estimates')
async def measurement_estimates() -> dict:
    raise HTTPException(
        410,
        "Still-image tailoring-point estimates are disabled until those points are validated. "
        "Stills are reference evidence only; use the slow-turn video workflow.",
    )


@app.post('/api/capture')
async def capture(
    view: str = Form(...), consent: bool = Form(False), session_id: str | None = Form(None),
    height_mm: float | None = Form(None), training_consent: bool = Form(False),
    file: UploadFile = File(...), user: SessionUser = Depends(current_user),
) -> dict:
    if not consent:
        raise HTTPException(403, 'Explicit consent is required before processing')
    if view not in CAPTURE_VIEWS:
        raise HTTPException(400, 'view must be front, side or back')
    try:
        capture_session_id = ensure_session(
            user, session_id, height_mm, training_consent, False,
        )
    except PermissionError as error:
        raise HTTPException(404, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    return await _process_capture_upload(user, capture_session_id, view, file)


async def _process_capture_upload(
    user: SessionUser, capture_session_id, view: str, file: UploadFile,
) -> dict:
    data = await file.read(MAX_CAPTURE_BYTES + 1)
    if len(data) > MAX_CAPTURE_BYTES:
        raise HTTPException(413, 'Image exceeds 20 MiB')
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR) if data else None
    if image is None or min(image.shape[:2]) < MIN_DIMENSION:
        raise HTTPException(400, 'Select a decodable image at least 64 pixels in each dimension')
    record = await asyncio.to_thread(capture_decision, view, image, data)
    record["measurementVision"] = {
        "status": "reference_only",
        "reason": "Still images are retained as human-review evidence and are not used to estimate measurements.",
    }
    persisted = await asyncio.to_thread(
        persist_analysis, user=user, session_id=capture_session_id, view=view, data=data,
        content_type=file.content_type or "application/octet-stream", record=record,
        width=image.shape[1], height=image.shape[0],
    )
    record.update(persisted)
    log.append(record)
    return record


@app.post('/api/captures')
async def capture_batch(
    consent: bool = Form(False), session_id: str | None = Form(None),
    height_mm: float | None = Form(None), training_consent: bool = Form(False),
    front: UploadFile = File(...), side: UploadFile = File(...), back: UploadFile = File(...),
    user: SessionUser = Depends(current_user),
) -> dict:
    """Authenticate once, then process all capture views in one shared session."""
    if not consent:
        raise HTTPException(403, 'Explicit consent is required before processing')
    try:
        capture_session_id = ensure_session(
            user, session_id, height_mm, training_consent, False,
        )
    except PermissionError as error:
        raise HTTPException(404, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    results = []
    try:
        for view, upload in (("front", front), ("side", side), ("back", back)):
            results.append(await _process_capture_upload(
                user, capture_session_id, view, upload,
            ))
    except Exception:
        # A newly-created batch must not leave private captures in a session ID
        # the client never received. Existing sessions remain recoverable by ID.
        if session_id is None:
            try:
                await asyncio.to_thread(
                    delete_capture_session, str(capture_session_id), owner_id=user.id,
                )
            except Exception:
                logger.exception("Could not roll back failed capture batch %s", capture_session_id)
        raise
    return {"captureSessionId": str(capture_session_id), "results": results}

# A slow turn is analysed by sampling a fixed number of frames across the clip, so
# the user does not need to time the recording precisely. This generous cap only
# rejects absurdly long uploads (the 50 MiB upload limit applies separately).
MAX_TURN_SECONDS = 90.0


def turn_coverage(
    reader, count: float, duration: float, height_mm: float | None = None,
    selected_frames: dict[str, np.ndarray] | None = None,
) -> dict:
    """Sample frames across a turn clip and derive view-orientation coverage."""
    pose = load_pose()
    model_available = pose is not None
    seen: set[str] = set()
    orientations = []
    back_measurements = None
    best_back_visibility = -1.0
    best_view_visibility: dict[str, float] = {}
    best_view_times: dict[str, float] = {}
    for i in range(20):
        fraction = (i + 0.5) / 20.0
        reader.set(cv2.CAP_PROP_POS_FRAMES, int(count * fraction))
        ok, frame = reader.read()
        if not ok:
            continue
        landmarks = estimate_pose(frame, pose)
        orientation = view_orientation(landmarks) if landmarks else 'unknown'
        if orientation in {'front', 'side', 'back'} and landmarks:
            visibility = min(
                landmarks[name].visibility
                for name in ('left_shoulder', 'right_shoulder', 'left_hip', 'right_hip')
            )
            if selected_frames is not None and visibility > best_view_visibility.get(orientation, -1.0):
                selected_frames[orientation] = frame.copy()
                best_view_visibility[orientation] = visibility
                best_view_times[orientation] = round(duration * fraction, 2)
        if orientation == 'back' and landmarks and height_mm is not None:
            if visibility > best_back_visibility:
                try:
                    back_measurements = estimate_back_measurements(frame, height_mm, landmarks)
                    back_measurements['timeSeconds'] = round(duration * fraction, 2)
                    best_back_visibility = visibility
                except ValueError:
                    pass
        if orientation != 'unknown':
            seen.add(orientation)
        orientations.append(dict(timeSeconds=round(duration * fraction, 2), orientation=orientation))

    required = {'front', 'back', 'side'}
    missing = sorted(required - seen)
    if not model_available:
        status = 'unknown'
    elif not missing:
        status = 'complete'
    else:
        status = 'incomplete'
    return dict(
        status=status,
        seenViews=sorted(seen),
        missingViews=missing,
        orientations=orientations,
        selectedViewFrames=best_view_times,
        method='pose-landmark orientation' if model_available else 'pose model unavailable',
        backMeasurements=back_measurements,
    )


@app.post('/api/turn-video')
async def turn_video(
    consent: bool = Form(False), session_id: str | None = Form(None),
    height_mm: float | None = Form(None),
    training_consent: bool = Form(False),
    calibration_kind: Annotated[str | None, Form()] = None,
    calibration_reference: Annotated[UploadFile | None, File()] = None,
    file: UploadFile = File(...), user: SessionUser = Depends(current_user),
) -> dict:
    """Bounded local video inspection; temporary source is always deleted."""
    import hashlib
    import os
    import tempfile
    import uuid
    from datetime import datetime, timezone
    if not consent:
        raise HTTPException(403, 'Explicit consent is required before processing')
    if height_mm is not None and not 1000 <= height_mm <= 2500:
        raise HTTPException(422, 'Height must be between 1000 and 2500 mm')

    calibration_image = None
    if calibration_reference is not None:
        if not calibration_kind:
            raise HTTPException(422, 'Choose the calibration reference type')
        calibration_data = await calibration_reference.read(MAX_CAPTURE_BYTES + 1)
        if len(calibration_data) > MAX_CAPTURE_BYTES:
            raise HTTPException(413, 'Calibration image exceeds 20 MiB')
        calibration_image = (
            cv2.imdecode(np.frombuffer(calibration_data, np.uint8), cv2.IMREAD_COLOR)
            if calibration_data else None
        )
        if calibration_image is None or min(calibration_image.shape[:2]) < MIN_DIMENSION:
            raise HTTPException(400, 'Select a decodable calibration image at least 64 pixels in each dimension')

    data = await file.read(50 * 1024 * 1024 + 1)
    if len(data) > 50 * 1024 * 1024:
        raise HTTPException(413, 'Video exceeds 50 MiB')
    path = None
    reader = None
    try:
        with tempfile.NamedTemporaryFile(suffix='.video', delete=False) as tmp:
            path = tmp.name
            tmp.write(data)
        reader = cv2.VideoCapture(path)
        fps = float(reader.get(cv2.CAP_PROP_FPS))
        count = float(reader.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = count / fps if fps > 0 else 0
        if not reader.isOpened() or not np.isfinite(duration) or duration <= 0:
            raise HTTPException(400, 'Video cannot be decoded; try MP4 or WebM')
        if duration > MAX_TURN_SECONDS:
            raise HTTPException(400, f'Video is too long to process; record one slow turn (maximum {int(MAX_TURN_SECONDS)} seconds).')
        samples = []
        for fraction in (.1, .3, .5, .7, .9):
            reader.set(cv2.CAP_PROP_POS_FRAMES, int(count * fraction))
            ok, frame = reader.read()
            if not ok: continue
            from .quality import evaluate_quality
            result = evaluate_quality(frame)
            samples.append(dict(timeSeconds=round(duration*fraction, 2),
                                quality='pass' if result.passed else 'fail', reasons=list(result.reasons)))

        selected_frames: dict[str, np.ndarray] = {}
        coverage = await asyncio.to_thread(
            turn_coverage, reader, count, duration, height_mm, selected_frames,
        )

        passed_sample_count = sum(sample["quality"] == "pass" for sample in samples)
        # A single transition frame should not suppress an otherwise usable turn.
        sample_quality_pass = len(samples) >= 4 and passed_sample_count >= 4
        reasons = []
        if not sample_quality_pass:
            reasons.append(
                'Some sampled frames are missing, blurry or poorly exposed. The video is kept for '
                'human review, but automated measurement estimates are withheld.'
            )
        if coverage['status'] == 'incomplete':
            reasons.append(
                'Turn coverage could not identify every view (missing '
                + ', '.join(coverage['missingViews'])
                + '). The video is kept for human review.'
            )
        elif coverage['status'] == 'complete':
            reasons.append('The turn shows front, side and back. Confirm it is a single continuous turn with neutral posture.')
        else:
            reasons.append('Rotation completeness could not be verified automatically; a reviewer must confirm a full turn.')

        calibration = {"status": "not_provided", "method": "height from selected video frames"}
        if calibration_image is not None and calibration_kind and height_mm is not None:
            try:
                reference_scale, reference_evidence = await asyncio.to_thread(
                    reference_scale_mm_per_pixel, calibration_image, calibration_kind,
                )
                body_scale = await asyncio.to_thread(
                    view_scale_mm_per_pixel, calibration_image, height_mm,
                )
                disagreement = abs(reference_scale - body_scale) / body_scale
                if disagreement <= 0.15:
                    calibration = {
                        "status": "accepted",
                        "method": "known object cross-check; height remains primary",
                        **reference_evidence,
                        "heightScaleMmPerPixel": round(body_scale, 6),
                        "disagreementPercent": round(disagreement * 100, 1),
                    }
                else:
                    calibration = {
                        "status": "rejected",
                        "method": "height fallback",
                        **reference_evidence,
                        "heightScaleMmPerPixel": round(body_scale, 6),
                        "disagreementPercent": round(disagreement * 100, 1),
                        "reason": "Reference and body scales differ by more than 15%; keep the object flat at the torso plane.",
                    }
            except ValueError as error:
                calibration = {
                    "status": "rejected", "method": "height fallback",
                    "reason": str(error),
                }

        measurement_estimates = None
        measurement_estimate_error = None
        if coverage['status'] == 'complete' and sample_quality_pass and height_mm is not None:
            try:
                geometry = await asyncio.to_thread(
                    estimate_circumferences,
                    selected_frames['front'], selected_frames['side'], height_mm,
                    selected_frames['back'],
                )
                back_estimates = coverage.get("backMeasurements")
                if back_estimates:
                    back_keys = {"across_back": "across_back", "nape_to_cb_waist": "nape_to_waist"}
                    for estimate in back_estimates.get("measurements", []):
                        measurement_key = back_keys.get(estimate.get("key"))
                        candidate = next(
                            (item for item in geometry["measurements"] if item["key"] == measurement_key),
                            None,
                        )
                        if candidate is not None:
                            candidate["value"] = estimate["value"]
                            candidate["rawValueMm"] = estimate["value"] * 10
                            candidate["confidence"] = estimate["confidence"]
                            candidate["sourceViews"] = ["back"]
                            candidate["provenance"] = back_estimates["method"]
                measurement_estimates = geometry
            except (KeyError, ValueError) as error:
                measurement_estimate_error = str(error)
                reasons.append(f'OpenCV measurement estimates unavailable: {measurement_estimate_error}')
        elif coverage['status'] == 'complete' and height_mm is None:
            measurement_estimate_error = 'Enter your height to calibrate video measurements.'
            reasons.append(measurement_estimate_error)
        elif coverage['status'] == 'complete' and not sample_quality_pass:
            measurement_estimate_error = 'Frame quality checks did not pass; no video measurements were generated.'
            reasons.append(measurement_estimate_error)

        record = dict(id=str(uuid.uuid4()), view='turn', decision='review',
                      imageFingerprint=dict(sha256=hashlib.sha256(data).hexdigest()),
                      checkedAt=datetime.now(timezone.utc).isoformat(), durationSeconds=round(duration,2),
                      samples=samples, turnCoverage=coverage, calibration=calibration, reasons=reasons,
                      scope='Sampled exposure/blur and pose-orientation turn coverage across the clip. '
                            'Posture quality and single-continuous-turn confirmation still require review.',
                      provisionalThresholds=True)
        try:
            capture_session_id = await asyncio.to_thread(
                ensure_session, user, session_id, height_mm, training_consent,
            )
        except PermissionError as error:
            raise HTTPException(404, str(error)) from error
        if measurement_estimates is not None:
            persisted_estimates = [
                {
                    "key": item["key"],
                    "valueMm": item["value"] * 10,
                    "sourceViews": item["sourceViews"],
                    "confidence": item["confidence"],
                }
                for item in measurement_estimates["measurements"]
            ]
            persistence = await asyncio.to_thread(
                persist_video_estimates,
                user=user, session_id=str(capture_session_id), estimates=persisted_estimates,
                model_version=measurement_estimates["modelVersion"],
            )
            record["measurementEstimates"] = {
                **measurement_estimates,
                **persistence,
                "calibration": calibration,
                "measurements": [
                    {**item, "requiresReview": True}
                    for item in measurement_estimates["measurements"]
                ],
                "warning": (
                    "Experimental MediaPipe/OpenCV video estimates require admin review and "
                    "confirmation against tape measurements."
                ),
            }
        elif measurement_estimate_error:
            record["measurementEstimateError"] = measurement_estimate_error
        record.update(await asyncio.to_thread(
            persist_analysis,
            user=user, session_id=capture_session_id, view="turn", data=data,
            content_type=file.content_type or "application/octet-stream", record=record,
            duration_seconds=duration,
        ))
        log.append(record)
        return record
    finally:
        if reader is not None: reader.release()
        if path: os.unlink(path)
