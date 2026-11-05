"""Persist private capture assets and their analysis metadata."""
from __future__ import annotations

import csv
import hashlib
import io
import logging
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
from tempfile import NamedTemporaryFile
from uuid import UUID, uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from psycopg.types.json import Jsonb

from .auth import SessionUser
from .database import connection
from .settings import get_settings
from .storage import delete_private, get_private, put_private, signed_download_url

logger = logging.getLogger(__name__)


def ensure_session(
    user: SessionUser, session_id: str | None, height_mm: float | None = None,
    training_consent: bool = False, external_vision_consent: bool | None = None,
) -> UUID:
    if height_mm is not None and not 1000 <= height_mm <= 2500:
        raise ValueError("Height must be between 1000 and 2500 mm")
    with connection() as conn:
        if session_id:
            row = conn.execute(
                "select id from capture_sessions where id = %s and customer_id = %s",
                (session_id, user.id),
            ).fetchone()
            if row is None:
                raise PermissionError("Capture session not found for this customer")
            if height_mm is not None:
                conn.execute("update capture_sessions set height_mm = %s where id = %s", (height_mm, row["id"]))
            if training_consent:
                conn.execute("update capture_sessions set training_consent = true where id = %s", (row["id"],))
            if external_vision_consent is not None:
                conn.execute(
                    "update capture_sessions set external_vision_consent = %s, "
                    "consent_version = 'visionfit-v3' where id = %s",
                    (external_vision_consent, row["id"]),
                )
            return row["id"]
        row = conn.execute(
            """insert into capture_sessions
                    (customer_id, created_by, height_mm, consented_at, consent_version,
                     training_consent, external_vision_consent, status)
                 values (%s, %s, %s, now(), 'visionfit-v3', %s, %s, 'processing') returning id""",
            (user.id, user.id, height_mm, training_consent, bool(external_vision_consent)),
        ).fetchone()
        return row["id"]


def delete_capture_session(
    session_id: str, *, owner_id: UUID | None = None, older_than: datetime | None = None,
) -> dict | None:
    """Delete one session and its private objects using a retryable two-phase flow.

    The database first records that deletion is in progress. Object deletion then
    happens outside a database transaction. If storage is temporarily unavailable,
    the row remains in deleting state with its object keys intact, so the same
    request or retention worker can safely retry.
    """
    conditions = ["id = %s"]
    params: list[object] = [session_id]
    if owner_id is not None:
        conditions.append("customer_id = %s")
        params.append(owner_id)
    if older_than is not None:
        conditions.append("(status = 'deleting' or updated_at < %s)")
        params.append(older_than)
    where = " and ".join(conditions)

    with connection() as conn:
        session = conn.execute(
            f"select id from capture_sessions where {where} for update", params,
        ).fetchone()
        if session is None:
            return None
        assets = conn.execute(
            "select storage_key from capture_assets where session_id = %s",
            (session["id"],),
        ).fetchall()
        conn.execute(
            "update capture_sessions set status = 'deleting' where id = %s",
            (session["id"],),
        )

    for asset in assets:
        delete_private(asset["storage_key"])

    with connection() as conn:
        # Eligibility and ownership were established before the deleting marker
        # updated updated_at; finalization therefore keys only on the locked ID.
        session = conn.execute(
            "select id from capture_sessions where id = %s for update",
            (session["id"],),
        ).fetchone()
        if session is None:
            return None
        deleted_tables = conn.execute(
            "delete from measurement_tables where capture_session_id = %s",
            (session["id"],),
        ).rowcount
        deleted = conn.execute(
            "delete from capture_sessions where id = %s returning id",
            (session["id"],),
        ).fetchone()
        if deleted is None:
            return None
    return {"assetsDeleted": len(assets), "measurementTablesDeleted": deleted_tables}


def purge_expired_capture_sessions(retention_days: int) -> int:
    """Remove sessions inactive beyond the configured retention period."""
    with connection() as conn:
        expired = conn.execute(
            "select id, customer_id from capture_sessions "
            "where status = 'deleting' or updated_at < now() - (%s * interval '1 day') "
            "order by updated_at",
            (retention_days,),
        ).fetchall()
    removed = 0
    for row in expired:
        result = delete_capture_session(
            str(row["id"]), owner_id=row["customer_id"],
            older_than=datetime.now(timezone.utc) - timedelta(days=retention_days),
        )
        if result is not None:
            removed += 1
    logger.info("Purged %d expired VisionFit capture sessions", removed)
    return removed


def persist_analysis(
    *, user: SessionUser, session_id: UUID, view: str, data: bytes, content_type: str,
    record: dict, width: int | None = None, height: int | None = None,
    duration_seconds: float | None = None,
) -> dict:
    suffix = Path(content_type.split(";", 1)[0]).suffix or {
        "image/jpeg": ".jpg", "image/png": ".png", "video/mp4": ".mp4", "video/webm": ".webm"
    }.get(content_type, ".bin")
    key = f"captures/{user.id}/{session_id}/{view}/{uuid4()}{suffix}"
    put_private(key, data, content_type)
    try:
        with connection() as conn:
            asset = conn.execute(
                """insert into capture_assets
                        (session_id, view, storage_provider, storage_key, content_type, byte_size,
                         sha256, width_px, height_px, duration_seconds, captured_at)
                     values (%s, %s, 'neon_object_storage', %s, %s, %s, %s, %s, %s, %s, now())
                     returning id""",
                (session_id, view, key, content_type, len(data), hashlib.sha256(data).hexdigest(),
                 width, height, duration_seconds),
            ).fetchone()
            measurement_vision = record.get("measurementVision", {})
            keypoint_workflow = measurement_vision.get("keypointWorkflow")
            model_name = "visionfit-capture+roboflow" if keypoint_workflow else "visionfit-opencv-mediapipe"
            model_version = keypoint_workflow or "vf2-posture-1"
            run = conn.execute(
                """insert into analysis_runs
                        (session_id, model_name, model_version, status, quality_decision,
                         calibration, started_at, completed_at)
                     values (%s, %s, %s, 'complete', %s, '{}'::jsonb, now(), now()) returning id""",
                (session_id, model_name, model_version, Jsonb(record)),
            ).fetchone()
            for item in record.get("evidence", []):
                if item.get("kind") not in {"pose-landmark", "tailoring-keypoint"} or not width or not height:
                    continue
                box = item["box"]
                label = item.get("label", "").removeprefix("pose landmark: ")
                source = "roboflow_keypoint" if item.get("kind") == "tailoring-keypoint" else "mediapipe_pose"
                conn.execute(
                    """insert into detected_landmarks
                            (analysis_run_id, asset_id, landmark_key, x_normalized, y_normalized,
                             visibility, source)
                         values (%s, %s, %s, %s, %s, %s, %s)
                         on conflict (analysis_run_id, asset_id, landmark_key) do nothing""",
                    (run["id"], asset["id"], label, box["x"] / width, box["y"] / height,
                     item.get("confidence", 1), source),
                )
            conn.execute("update capture_sessions set status = 'complete' where id = %s", (session_id,))
        return {
            "captureSessionId": str(session_id), "assetId": str(asset["id"]),
            "analysisRunId": str(run["id"]),
        }
    except Exception:
        delete_private(key)
        raise


def session_tailoring_keypoints(user: SessionUser, session_id: str) -> dict[str, list[dict]]:
    """Return the latest stored Roboflow points per capture view for this customer."""
    with connection() as conn:
        session = conn.execute(
            "select id from capture_sessions where id::text = %s and customer_id = %s",
            (session_id, user.id),
        ).fetchone()
        if session is None:
            raise PermissionError("Capture session not found for this customer")
        rows = conn.execute(
            """select distinct on (asset.view, landmark.landmark_key)
                      asset.view::text view, landmark.landmark_key,
                      landmark.x_normalized, landmark.y_normalized, landmark.visibility
                 from detected_landmarks landmark
                 join analysis_runs run on run.id = landmark.analysis_run_id
                 join capture_assets asset on asset.id = landmark.asset_id
                where run.session_id = %s and landmark.source = 'roboflow_keypoint'
                  and asset.view in ('front','side','back')
                order by asset.view, landmark.landmark_key, run.created_at desc""",
            (session["id"],),
        ).fetchall()
    points: dict[str, list[dict]] = {"front": [], "side": [], "back": []}
    for row in rows:
        points[row["view"]].append({
            "name": row["landmark_key"], "x": float(row["x_normalized"]),
            "y": float(row["y_normalized"]),
            "confidence": float(row["visibility"] if row["visibility"] is not None else 1),
        })
    return points


def recent_decisions(limit: int) -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            """select ar.id, ar.session_id, ar.status::text, ar.model_name, ar.model_version,
                      ar.quality_decision, ar.created_at, u.email customer_email
                 from analysis_runs ar
                 join capture_sessions cs on cs.id = ar.session_id
                 join app_users u on u.id = cs.customer_id
                order by ar.created_at desc limit %s""",
            (max(1, min(limit, 100)),),
        ).fetchall()
    return [
        {"id": str(row["id"]), "sessionId": str(row["session_id"]),
         "customerEmail": row["customer_email"], "status": row["status"],
         "modelName": row["model_name"], "modelVersion": row["model_version"],
         "qualityDecision": row["quality_decision"], "createdAt": row["created_at"].isoformat()}
        for row in rows
    ]


def admin_capture_sessions(limit: int = 100) -> list[dict]:
    """List capture sessions for review without exposing private storage keys."""
    with connection() as conn:
        rows = conn.execute(
            """select cs.id, cs.customer_id, u.email, u.display_name, u.role::text,
                      cs.height_mm, cs.status::text, cs.consented_at, cs.training_consent, cs.created_at,
                      cs.updated_at, count(distinct ca.id) asset_count,
                      count(distinct ar.id) analysis_count,
                      array_remove(array_agg(distinct ca.view::text), null) views,
                      max(ar.created_at) latest_analysis_at
                 from capture_sessions cs
                 join app_users u on u.id = cs.customer_id
                 left join capture_assets ca on ca.session_id = cs.id
                 left join analysis_runs ar on ar.session_id = cs.id
                group by cs.id, u.id
                order by cs.created_at desc limit %s""",
            (max(1, min(limit, 500)),),
        ).fetchall()
    return [
        {
            "id": str(row["id"]), "customerId": str(row["customer_id"]),
            "customerEmail": row["email"], "customerName": row["display_name"],
            "customerRole": row["role"],
            "heightMm": None if row["height_mm"] is None else float(row["height_mm"]),
            "status": row["status"], "views": row["views"],
            "trainingConsent": row["training_consent"],
            "assetCount": row["asset_count"], "analysisCount": row["analysis_count"],
            "consentedAt": row["consented_at"].isoformat() if row["consented_at"] else None,
            "createdAt": row["created_at"].isoformat(),
            "updatedAt": row["updated_at"].isoformat(),
            "latestAnalysisAt": row["latest_analysis_at"].isoformat() if row["latest_analysis_at"] else None,
        }
        for row in rows
    ]


def admin_capture_session(session_id: str) -> dict | None:
    """Return review evidence and short-lived private asset links for one session."""
    with connection() as conn:
        session = conn.execute(
            """select cs.id, cs.customer_id, u.email, u.display_name, u.role::text,
                      cs.height_mm, cs.status::text, cs.consented_at, cs.consent_version,
                      cs.training_consent, cs.external_vision_consent, cs.notes,
                      cs.created_at, cs.updated_at
                 from capture_sessions cs join app_users u on u.id = cs.customer_id
                where cs.id = %s""",
            (session_id,),
        ).fetchone()
        if session is None:
            return None
        assets = conn.execute(
            """select id, view::text, storage_key, content_type, byte_size, sha256,
                      width_px, height_px, duration_seconds, captured_at, created_at
                 from capture_assets where session_id = %s order by created_at""",
            (session_id,),
        ).fetchall()
        runs = conn.execute(
            """select id, model_name, model_version, status::text, quality_decision,
                      calibration, error_message, started_at, completed_at, created_at
                 from analysis_runs where session_id = %s order by created_at desc""",
            (session_id,),
        ).fetchall()
        landmarks = conn.execute(
            """select dl.id, dl.analysis_run_id, dl.asset_id, dl.landmark_key,
                      dl.x_normalized, dl.y_normalized, dl.z_relative, dl.visibility,
                      dl.source, dl.manually_adjusted
                 from detected_landmarks dl join analysis_runs ar on ar.id = dl.analysis_run_id
                where ar.session_id = %s order by dl.landmark_key""",
            (session_id,),
        ).fetchall()
    return {
        "id": str(session["id"]), "customerId": str(session["customer_id"]),
        "customerEmail": session["email"], "customerName": session["display_name"],
        "customerRole": session["role"],
        "heightMm": None if session["height_mm"] is None else float(session["height_mm"]),
        "status": session["status"], "consentedAt": session["consented_at"].isoformat() if session["consented_at"] else None,
        "consentVersion": session["consent_version"], "trainingConsent": session["training_consent"],
        "externalVisionConsent": session["external_vision_consent"], "notes": session["notes"],
        "createdAt": session["created_at"].isoformat(), "updatedAt": session["updated_at"].isoformat(),
        "assets": [
            {
                "id": str(row["id"]), "view": row["view"], "contentType": row["content_type"],
                "byteSize": row["byte_size"], "sha256": row["sha256"],
                "widthPx": row["width_px"], "heightPx": row["height_px"],
                "durationSeconds": float(row["duration_seconds"]) if row["duration_seconds"] is not None else None,
                "capturedAt": row["captured_at"].isoformat() if row["captured_at"] else None,
                "createdAt": row["created_at"].isoformat(),
                "reviewUrl": signed_download_url(row["storage_key"]) if session["training_consent"] else None,
            }
            for row in assets
        ],
        "analysisRuns": [
            {
                "id": str(row["id"]), "modelName": row["model_name"],
                "modelVersion": row["model_version"], "status": row["status"],
                "qualityDecision": row["quality_decision"], "calibration": row["calibration"],
                "errorMessage": row["error_message"],
                "startedAt": row["started_at"].isoformat() if row["started_at"] else None,
                "completedAt": row["completed_at"].isoformat() if row["completed_at"] else None,
                "createdAt": row["created_at"].isoformat(),
            }
            for row in runs
        ],
        "landmarks": [
            {
                "id": row["id"], "analysisRunId": str(row["analysis_run_id"]),
                "assetId": str(row["asset_id"]), "key": row["landmark_key"],
                "x": float(row["x_normalized"]), "y": float(row["y_normalized"]),
                "z": float(row["z_relative"]) if row["z_relative"] is not None else None,
                "visibility": float(row["visibility"]) if row["visibility"] is not None else None,
                "source": row["source"], "manuallyAdjusted": row["manually_adjusted"],
            }
            for row in landmarks
        ],
    }


def create_training_export() -> tuple[str, int]:
    """Create a ZIP of images from sessions with explicit model-training consent."""
    with connection() as conn:
        rows = conn.execute(
            """select cs.id session_id, cs.customer_id, cs.consent_version, cs.consented_at,
                      ca.view::text view, ca.storage_key, ca.content_type, ca.sha256
                 from capture_sessions cs
                 join capture_assets ca on ca.session_id = cs.id
                where cs.training_consent = true
                  and cs.status <> 'deleting'
                  and lower(split_part(ca.content_type, ';', 1)) like 'image/%'
                order by cs.customer_id, cs.id, ca.created_at, ca.id"""
        ).fetchall()

    subject_ids: dict[str, str] = {}
    source_groups: dict[str, str] = {}
    manifest = io.StringIO(newline="")
    writer = csv.DictWriter(
        manifest,
        fieldnames=(
            "path", "subject_id", "source_group", "view", "content_type", "sha256",
            "training_consent", "consent_version", "consented_at",
        ),
    )
    writer.writeheader()
    temp = NamedTemporaryFile(prefix="visionfit-training-", suffix=".zip", delete=False)
    export_path = temp.name
    temp.close()
    try:
        with ZipFile(export_path, "w", compression=ZIP_DEFLATED) as archive:
            for index, row in enumerate(rows, start=1):
                customer_id = str(row["customer_id"])
                session_id = str(row["session_id"])
                subject_id = subject_ids.setdefault(customer_id, f"subject-{len(subject_ids) + 1:04d}")
                source_group = source_groups.setdefault(session_id, f"sequence-{len(source_groups) + 1:04d}")
                content_type = row["content_type"].split(";", 1)[0].lower()
                extension = {
                    "image/jpeg": ".jpg",
                    "image/png": ".png",
                    "image/webp": ".webp",
                }.get(content_type, ".img")
                relative_path = (
                    f"images/{subject_id}/{source_group}_{row['view']}_{index:05d}{extension}"
                )
                archive.writestr(relative_path, get_private(row["storage_key"]))
                consented_at = row["consented_at"]
                writer.writerow({
                    "path": relative_path,
                    "subject_id": subject_id,
                    "source_group": source_group,
                    "view": row["view"],
                    "content_type": content_type,
                    "sha256": row["sha256"],
                    "training_consent": "true",
                    "consent_version": row["consent_version"],
                    "consented_at": consented_at.isoformat()
                    if isinstance(consented_at, datetime) else str(consented_at or ""),
                })
            archive.writestr("manifest.csv", manifest.getvalue())
        return export_path, len(rows)
    except Exception:
        os.unlink(export_path)
        raise
