"""Versioned measurement registry and Neon-backed measurement tables.

Measurements are stored canonically in millimetres.  This module deliberately
separates the table contract from vision inference: capture analysis may propose
a value later, but it must also state its method, source views and confidence.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from psycopg.types.json import Jsonb

from .auth import SessionUser, require_admin
from .database import connection

Unit = Literal["mm", "cm", "in"]
View = Literal["front", "side", "back"]
Status = Literal["pending", "estimated", "reviewed", "unavailable"]

REGISTRY_VERSION = "2.2.0"
BODY_MEASUREMENT_POLICY = (
    "Exact body measurement — no garment ease or seam allowance. "
    "Ease is controlled in Pattern CAD."
)
IMAGE_PLANE_WARNING = (
    "Image-plane distances are not body-surface lengths or circumferences. "
    "A measurement value requires calibrated scale and the declared measurement path."
)


@dataclass(frozen=True)
class MeasurementDefinition:
    key: str
    display_name: str
    scope: Literal["core", "future"]
    category: str
    path: Literal["circumference", "straight", "surface"]
    required_views: tuple[View, ...]
    required_landmarks: tuple[str, ...]
    calculation: str
    pattern_cad_names: tuple[str, ...]
    pattern_cad_landmark: str | None


DEFINITIONS = (
    MeasurementDefinition("bust", "Bust", "core", "Circumference", "circumference", ("front", "back"), ("bust_level_left_side", "bust_point_left", "bust_level_center_front", "bust_point_right", "bust_level_right_side", "bust_level_center_back"), "manual_only", ("bust", "full bust"), "bust"),
    MeasurementDefinition("underbust", "Underbust", "core", "Circumference", "circumference", ("front", "side"), ("underbust_left", "underbust_right"), "manual_only", ("under bust", "underbust"), "underBust"),
    MeasurementDefinition("bust_point", "Bust point length", "core", "Bust control", "surface", ("front", "side"), ("side_neck_left", "bust_point_left"), "manual_only", ("bust point", "bust point length"), None),
    MeasurementDefinition("bust_span", "Bust span", "core", "Bust control", "straight", ("front",), ("bust_point_left", "bust_point_right"), "manual_only", ("bust span",), None),
    MeasurementDefinition("bust_radius", "Bust radius", "core", "Bust control", "straight", ("front", "side"), ("bust_point_left", "underbust_left"), "manual_only", ("bust radius",), None),
    MeasurementDefinition("waist", "Waist", "core", "Circumference", "circumference", ("front", "back"), ("waist_left_side", "waist_center_front", "waist_right_side", "waist_center_back"), "manual_only", ("waist", "natural waist"), "waist"),
    MeasurementDefinition("hip", "Hip", "core", "Circumference", "circumference", ("front", "back"), ("hip_side_left", "hip_center_front", "hip_side_right", "hip_center_back"), "manual_only", ("hip", "full hip", "seat"), "hip"),
    MeasurementDefinition("front_shoulder", "Front shoulder", "core", "Upper body width", "straight", ("front",), ("shoulder_point_left", "shoulder_point_right"), "manual_only", ("front shoulder", "shoulder width", "across shoulder"), "shoulder"),
    MeasurementDefinition("back_shoulder", "Back shoulder", "core", "Upper body width", "surface", ("back",), ("shoulder_point_left", "shoulder_point_right"), "manual_only", ("back shoulder",), "shoulder"),
    MeasurementDefinition("across_chest", "Across chest", "core", "Upper body width", "surface", ("front",), ("across_chest_left", "across_chest_right"), "manual_only", ("across chest", "chest width"), "acrossChest"),
    MeasurementDefinition("across_back", "Across back", "core", "Upper body width", "surface", ("back",), ("across_back_left", "across_back_right"), "manual_only", ("across back",), None),
    MeasurementDefinition("nape_to_waist", "Nape to waist", "core", "Vertical length", "straight", ("back",), ("nape", "waist_center_back"), "manual_only", ("nape to waist", "back length"), "napeToWaist"),
    MeasurementDefinition("full_front_length", "Full front length", "core", "Vertical length", "surface", ("front", "side"), ("side_neck_left", "bust_point_left", "waist_below_bust_left"), "manual_only", ("full front length",), None),
    MeasurementDefinition("side_waist_to_knee", "Side waist to knee", "future", "Lower body length", "surface", ("side",), ("waist_right_side", "knee_right"), "manual_only", ("side waist to knee", "waist to knee"), "sideWaistToKnee"),
)
DEFINITION_BY_KEY = {definition.key: definition for definition in DEFINITIONS}


def _to_mm(value: float, unit: Unit) -> float:
    return value if unit == "mm" else value * 10 if unit == "cm" else value * 25.4


def _from_mm(value: float, unit: Unit) -> float:
    converted = value if unit == "mm" else value / 10 if unit == "cm" else value / 25.4
    return round(converted, 2)


class CreateTableRequest(BaseModel):
    subject_id: str = Field(min_length=1, max_length=200)
    capture_session_id: str | None = Field(default=None, max_length=100)
    unit: Unit = "cm"


class MeasurementValueRequest(BaseModel):
    value: float = Field(gt=0)
    unit: Unit = "cm"
    status: Literal["estimated", "reviewed"] = "estimated"
    method: str = Field(min_length=1, max_length=200)
    source_views: list[View] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)
    notes: str = Field(default="", max_length=1000)


class MeasurementPathRequest(BaseModel):
    path: Literal["circumference", "straight", "surface"]
    closed: bool = False
    ordered_points: list[str] = Field(min_length=2, max_length=30)
    segment_views: list[View] = Field(min_length=1, max_length=30)
    required_views: list[View] = Field(min_length=1, max_length=3)
    calculation_method: str = Field(min_length=1, max_length=200)


def validate_measurement_path(request: MeasurementPathRequest) -> None:
    points = request.ordered_points
    if any(not re.fullmatch(r"[a-z][a-z0-9_]{1,79}", point) for point in points):
        raise HTTPException(422, "Point keys must use lowercase snake_case")
    if len(set(points)) != len(points):
        raise HTTPException(422, "Each point belongs in the sequence once; closed paths close automatically")
    if request.path == "straight" and len(points) != 2:
        raise HTTPException(422, "Straight measurements require exactly two ordered points")
    if request.path == "circumference" and (not request.closed or len(points) < 3):
        raise HTTPException(422, "Circumference measurements require a closed path with at least three points")
    if request.path != "circumference" and request.closed:
        raise HTTPException(422, "Only circumference measurements may be closed")
    expected_segments = len(points) - 1 + int(request.closed)
    if len(request.segment_views) != expected_segments:
        raise HTTPException(422, f"Path requires exactly {expected_segments} segment views")
    unexpected_segment_views = sorted(set(request.segment_views) - set(request.required_views))
    if unexpected_segment_views:
        raise HTTPException(422, "Every segment view must also be selected as a required view")


router = APIRouter(prefix="/api", tags=["measurements"])


def _path_json(row: dict) -> dict:
    return {
        "id": str(row["id"]), "measurementKey": row["measurement_key"],
        "displayName": row["display_name"], "version": row["version"],
        "status": row["status"], "path": row["path"], "closed": row["closed"],
        "orderedPoints": row["ordered_points"], "segmentViews": row["segment_views"],
        "requiredViews": row["required_views"],
        "calculationMethod": row["calculation_method"],
        "publishedAt": row["published_at"].isoformat() if row["published_at"] else None,
    }


def published_measurement_paths() -> list[dict]:
    """Load the immutable path versions used by the runtime estimator."""
    with connection() as conn:
        rows = conn.execute(
            """select v.id, v.measurement_key, d.display_name, v.version, v.status::text,
                      v.path::text, v.closed, v.ordered_points, v.segment_views,
                      v.required_views::text[],
                      v.calculation_method, v.published_at
                 from measurement_definition_versions v
                 join measurement_definitions d on d.key = v.measurement_key
                where v.status = 'published' and v.calculation_method = 'ordered_keypoint_path'
                  and d.active order by d.created_at, v.measurement_key"""
        ).fetchall()
    return [_path_json(row) for row in rows]


@router.get("/admin/measurement-paths")
async def list_measurement_paths(_admin: SessionUser = Depends(require_admin)) -> dict:
    with connection() as conn:
        rows = conn.execute(
            """select v.id, v.measurement_key, d.display_name, v.version, v.status::text,
                      v.path::text, v.closed, v.ordered_points, v.segment_views,
                      v.required_views::text[],
                      v.calculation_method, v.published_at
                 from measurement_definition_versions v
                 join measurement_definitions d on d.key = v.measurement_key
                where v.status in ('draft', 'published')
                order by d.created_at, v.measurement_key, v.status"""
        ).fetchall()
    return {"paths": [_path_json(row) for row in rows]}


@router.put("/admin/measurement-paths/{key}/draft")
async def save_measurement_path_draft(
    key: str, request: MeasurementPathRequest, admin: SessionUser = Depends(require_admin),
) -> dict:
    validate_measurement_path(request)
    views = list(dict.fromkeys(request.required_views))
    with connection() as conn:
        definition = conn.execute("select display_name from measurement_definitions where key = %s", (key,)).fetchone()
        if definition is None:
            raise HTTPException(404, "Unknown measurement key")
        row = conn.execute(
            """insert into measurement_definition_versions
                    (measurement_key, version, status, path, closed, ordered_points,
                     segment_views, required_views, calculation_method, created_by)
                 values (%s, coalesce((select max(version) + 1 from measurement_definition_versions
                                        where measurement_key = %s), 1),
                         'draft', %s, %s, %s, %s, %s::capture_view[], %s, %s)
                 on conflict (measurement_key) where status = 'draft' do update set
                    path = excluded.path, closed = excluded.closed, ordered_points = excluded.ordered_points,
                    segment_views = excluded.segment_views,
                    required_views = excluded.required_views, calculation_method = excluded.calculation_method
                 returning id, measurement_key, version, status::text, path::text, closed,
                           ordered_points, segment_views, required_views::text[], calculation_method, published_at""",
            (key, key, request.path, request.closed, Jsonb(request.ordered_points),
             Jsonb(request.segment_views), views,
             request.calculation_method, admin.id),
        ).fetchone()
    row["display_name"] = definition["display_name"]
    return _path_json(row)


@router.post("/admin/measurement-paths/{key}/publish")
async def publish_measurement_path(
    _key: str, _admin: SessionUser = Depends(require_admin),
) -> dict:
    raise HTTPException(
        409,
        "Tailoring-point paths are not publishable until their labels are validated against tape measurements.",
    )


def _definition_json(definition: MeasurementDefinition) -> dict:
    data = asdict(definition)
    return {
        "key": data["key"],
        "displayName": data["display_name"],
        "scope": data["scope"],
        "category": data["category"],
        "path": data["path"],
        "requiredViews": list(data["required_views"]),
        "requiredLandmarks": list(data["required_landmarks"]),
        "calculation": data["calculation"],
        "patternCadNames": list(data["pattern_cad_names"]),
        "patternCadLandmark": data["pattern_cad_landmark"],
    }


def _load_table(table_id: str, unit: Unit) -> dict | None:
    with connection() as conn:
        table = conn.execute(
            """select mt.id, mt.registry_version, mt.created_at, mt.updated_at,
                      u.id customer_id, u.email customer_email
                 from measurement_tables mt join app_users u on u.id = mt.customer_id
                where mt.id = %s""",
            (table_id,),
        ).fetchone()
        if table is None:
            return None
        rows = conn.execute(
            """select d.key, d.display_name, d.scope, d.category,
                      version.version path_version, version.path::text,
                      version.required_views::text[], version.ordered_points required_landmarks,
                      version.segment_views, version.calculation_method,
                      d.pattern_cad_names, d.pattern_cad_landmark,
                      v.value_mm, v.status::text, v.method, v.source_views::text[],
                      v.confidence, v.notes
                 from measurement_values v
                 join measurement_definitions d on d.key = v.measurement_key
                 join measurement_definition_versions version on version.id = v.definition_version_id
                where v.table_id = %s
                order by d.created_at, d.key""",
            (table_id,),
        ).fetchall()
    return {
        "id": str(table["id"]),
        "subjectId": str(table["customer_id"]),
        "subjectEmail": table["customer_email"],
        "registryVersion": table["registry_version"],
        "createdAt": table["created_at"].isoformat(),
        "updatedAt": table["updated_at"].isoformat(),
        "unit": unit,
        "rows": [
            {
                "key": row["key"], "displayName": row["display_name"], "scope": row["scope"],
                "category": row["category"], "path": row["path"],
                "requiredViews": row["required_views"], "requiredLandmarks": row["required_landmarks"],
                "segmentViews": row["segment_views"], "pathVersion": row["path_version"],
                "calculation": row["calculation_method"], "patternCadNames": row["pattern_cad_names"],
                "patternCadLandmark": row["pattern_cad_landmark"],
                "value": None if row["value_mm"] is None else _from_mm(float(row["value_mm"]), unit),
                "unit": unit, "status": row["status"], "method": row["method"],
                "sourceViews": row["source_views"],
                "confidence": None if row["confidence"] is None else float(row["confidence"]),
                "notes": row["notes"], "requiresReview": row["status"] != "reviewed",
            }
            for row in rows
        ],
    }


@router.get("/measurements/definitions")
async def measurement_definitions(scope: Literal["core", "future", "all"] = Query("all")) -> dict:
    selected = DEFINITIONS if scope == "all" else tuple(d for d in DEFINITIONS if d.scope == scope)
    return {
        "version": REGISTRY_VERSION,
        "bodyMeasurementPolicy": BODY_MEASUREMENT_POLICY,
        "warning": IMAGE_PLANE_WARNING,
        "definitions": [_definition_json(definition) for definition in selected],
    }


@router.post("/measurement-tables", status_code=201)
async def create_measurement_table(
    request: CreateTableRequest, admin: SessionUser = Depends(require_admin)
) -> dict:
    existing_table_id = None
    with connection() as conn:
        customer = conn.execute(
            "select id from app_users where id::text = %s or lower(email) = lower(%s)",
            (request.subject_id, request.subject_id),
        ).fetchone()
        if customer is None:
            raise HTTPException(404, "Customer not found; the customer must sign in first")
        if request.capture_session_id:
            capture = conn.execute(
                "select id from capture_sessions where id::text = %s and customer_id = %s",
                (request.capture_session_id, customer["id"]),
            ).fetchone()
            if capture is None:
                raise HTTPException(404, "Capture session not found for this person")
            existing = conn.execute(
                """select id from measurement_tables
                    where customer_id = %s and capture_session_id = %s
                    order by created_at desc limit 1""",
                (customer["id"], capture["id"]),
            ).fetchone()
            if existing is not None:
                existing_table_id = existing["id"]
        if existing_table_id is None:
            table = conn.execute(
                """insert into measurement_tables
                        (customer_id, capture_session_id, registry_version, preferred_unit, created_by)
                     values (%s, %s, %s, %s, %s) returning id""",
                (customer["id"], request.capture_session_id, REGISTRY_VERSION, request.unit, admin.id),
            ).fetchone()
    if existing_table_id is not None:
        return _load_table(str(existing_table_id), request.unit)
    return _load_table(str(table["id"]), request.unit)


@router.get("/admin/capture-sessions/{session_id}/measurement-table")
async def get_capture_measurement_table(
    session_id: str, _admin: SessionUser = Depends(require_admin),
) -> dict | None:
    with connection() as conn:
        table = conn.execute(
            """select id from measurement_tables
                where capture_session_id::text = %s
                order by created_at desc limit 1""",
            (session_id,),
        ).fetchone()
    return _load_table(str(table["id"]), "cm") if table else None


@router.get("/measurement-tables/{table_id}")
async def get_measurement_table(
    table_id: str, unit: Unit = Query("cm"), _admin: SessionUser = Depends(require_admin)
) -> dict:
    table = _load_table(table_id, unit)
    if table is None:
        raise HTTPException(404, "Measurement table not found")
    return table


@router.put("/measurement-tables/{table_id}/measurements/{key}")
async def set_measurement_value(
    table_id: str,
    key: str,
    request: MeasurementValueRequest,
    unit: Unit = Query("cm"),
    admin: SessionUser = Depends(require_admin),
) -> dict:
    if key not in DEFINITION_BY_KEY:
        raise HTTPException(404, "Unknown measurement key")
    if request.status == "estimated" and request.confidence is None:
        raise HTTPException(422, "Estimated measurements require confidence")
    reviewed = request.status == "reviewed"
    with connection() as conn:
        pinned = conn.execute(
            """select version.required_views::text[] required_views
                 from measurement_values value
                 join measurement_definition_versions version on version.id = value.definition_version_id
                where value.table_id = %s and value.measurement_key = %s""",
            (table_id, key),
        ).fetchone()
        if pinned is None:
            raise HTTPException(404, "Measurement table or measurement row not found")
        unexpected_views = (
            sorted(set(request.source_views) - set(pinned["required_views"]))
            if request.method != "admin_review" else []
        )
        if unexpected_views:
            raise HTTPException(422, f"Views not declared by this table's {key} version: {', '.join(unexpected_views)}")
        updated = conn.execute(
            """update measurement_values
                  set value_mm = %s, status = %s, method = %s, source_views = %s::capture_view[],
                      confidence = %s, notes = %s, reviewed_by = %s,
                      reviewed_at = case when %s then now() else null end
                where table_id = %s and measurement_key = %s returning id""",
            (round(_to_mm(request.value, request.unit), 3), request.status, request.method,
             list(dict.fromkeys(request.source_views)), request.confidence, request.notes,
             admin.id if reviewed else None, reviewed, table_id, key),
        ).fetchone()
        if updated is None:
            raise HTTPException(404, "Measurement table not found")
    return _load_table(table_id, unit)


def persist_runtime_estimates(
    *, user: SessionUser, session_id: str, estimates: list[dict], model_version: str,
) -> dict:
    """Link review-only estimates to the customer's capture and pinned path versions."""
    with connection() as conn:
        capture = conn.execute(
            "select id, customer_id from capture_sessions where id::text = %s and customer_id = %s",
            (session_id, user.id),
        ).fetchone()
        if capture is None:
            raise PermissionError("Capture session not found for this customer")
        table = conn.execute(
            """select id from measurement_tables
                where capture_session_id = %s and customer_id = %s
                order by created_at desc limit 1""",
            (capture["id"], user.id),
        ).fetchone()
        if table is None:
            table = conn.execute(
                """insert into measurement_tables
                        (customer_id, capture_session_id, registry_version, preferred_unit, created_by)
                     values (%s, %s, %s, 'cm', %s) returning id""",
                (user.id, capture["id"], REGISTRY_VERSION, user.id),
            ).fetchone()
        persisted: list[str] = []
        skipped: list[str] = []
        for estimate in estimates:
            updated = conn.execute(
                """update measurement_values
                      set value_mm = %s, status = 'estimated', method = 'ordered_keypoint_path',
                          source_views = %s::capture_view[], confidence = %s,
                          notes = %s, reviewed_by = null, reviewed_at = null
                    where table_id = %s and measurement_key = %s
                      and definition_version_id = %s and status <> 'reviewed'
                    returning id""",
                (estimate["valueMm"], estimate["sourceViews"], estimate["confidence"],
                 f"Calibration model {model_version}; review required", table["id"],
                 estimate["key"], estimate["pathVersionId"]),
            ).fetchone()
            (persisted if updated else skipped).append(estimate["key"])
        conn.execute(
            """insert into audit_events (actor_id, entity_type, entity_id, action, after_data)
                 values (%s, 'measurement_table', %s, 'runtime_estimates', %s)""",
            (user.id, str(table["id"]), Jsonb({"persisted": persisted, "skipped": skipped,
                                               "modelVersion": model_version})),
        )
    return {"measurementTableId": str(table["id"]), "persistedKeys": persisted, "skippedKeys": skipped}


def persist_video_estimates(
    *, user: SessionUser, session_id: str, estimates: list[dict], model_version: str,
) -> dict:
    """Save MediaPipe/OpenCV video candidates for admin review without replacing reviewed values."""
    with connection() as conn:
        capture = conn.execute(
            "select id, customer_id from capture_sessions where id::text = %s and customer_id = %s",
            (session_id, user.id),
        ).fetchone()
        if capture is None:
            raise PermissionError("Capture session not found for this customer")
        table = conn.execute(
            """select id from measurement_tables
                where capture_session_id = %s and customer_id = %s
                order by created_at desc limit 1""",
            (capture["id"], user.id),
        ).fetchone()
        if table is None:
            table = conn.execute(
                """insert into measurement_tables
                        (customer_id, capture_session_id, registry_version, preferred_unit, created_by)
                     values (%s, %s, %s, 'cm', %s) returning id""",
                (user.id, capture["id"], REGISTRY_VERSION, user.id),
            ).fetchone()

        persisted: list[str] = []
        skipped: list[str] = []
        for estimate in estimates:
            updated = conn.execute(
                """update measurement_values
                      set value_mm = %s, status = 'estimated', method = 'mediapipe_opencv_video',
                          source_views = %s::capture_view[], confidence = %s,
                          notes = %s, reviewed_by = null, reviewed_at = null
                    where table_id = %s and measurement_key = %s and status <> 'reviewed'
                    returning id""",
                (
                    estimate["valueMm"], estimate["sourceViews"], estimate["confidence"],
                    f"Video geometry model {model_version}; human review required",
                    table["id"], estimate["key"],
                ),
            ).fetchone()
            (persisted if updated else skipped).append(estimate["key"])
        conn.execute(
            """insert into audit_events (actor_id, entity_type, entity_id, action, after_data)
                 values (%s, 'measurement_table', %s, 'video_estimates', %s)""",
            (user.id, str(table["id"]), Jsonb({
                "persisted": persisted, "skipped": skipped, "modelVersion": model_version,
            })),
        )
    return {"measurementTableId": str(table["id"]), "persistedKeys": persisted, "skippedKeys": skipped}


@router.get("/admin/customers")
async def list_customers(_admin: SessionUser = Depends(require_admin)) -> dict:
    with connection() as conn:
        rows = conn.execute(
            """select u.id, u.email, u.display_name, u.role::text,
                      count(distinct cs.id) capture_count, max(cs.created_at) latest_capture_at
                 from app_users u left join capture_sessions cs on cs.customer_id = u.id
                where u.active
                group by u.id order by max(cs.created_at) desc nulls last, u.created_at desc"""
        ).fetchall()
    return {"customers": [
        {"id": str(row["id"]), "email": row["email"], "displayName": row["display_name"],
         "role": row["role"], "captureCount": row["capture_count"],
         "latestCaptureAt": row["latest_capture_at"].isoformat() if row["latest_capture_at"] else None}
        for row in rows
    ]}


@router.get("/admin/capture-sessions/{session_id}/measurement-analysis")
async def measurement_analysis(session_id: str, _admin: SessionUser = Depends(require_admin)) -> dict:
    """Explain whether each measurement has the capture evidence it declares."""
    with connection() as conn:
        session = conn.execute(
            "select id, height_mm from capture_sessions where id::text = %s", (session_id,),
        ).fetchone()
        if session is None:
            raise HTTPException(404, "Capture session not found")
        view_rows = conn.execute(
            "select distinct view::text view from capture_assets where session_id = %s", (session_id,),
        ).fetchall()
        landmark_rows = conn.execute(
            """select distinct asset.view::text view, dl.landmark_key from detected_landmarks dl
                 join analysis_runs ar on ar.id = dl.analysis_run_id
                 join capture_assets asset on asset.id = dl.asset_id
                where ar.session_id = %s""",
            (session_id,),
        ).fetchall()
    available_views = {row["view"] for row in view_rows}
    available_landmarks = {row["landmark_key"] for row in landmark_rows}
    landmarks_by_view = {
        view: {row["landmark_key"] for row in landmark_rows if row["view"] == view}
        for view in available_views
    }
    runtime_paths = {path["measurementKey"]: path for path in published_measurement_paths()}
    analyses = []
    for definition in DEFINITIONS:
        definition_data = _definition_json(definition)
        runtime = runtime_paths.get(definition.key)
        required_views = runtime["requiredViews"] if runtime else definition_data["requiredViews"]
        required_points = runtime["orderedPoints"] if runtime else definition_data["requiredLandmarks"]
        calculation = runtime["calculationMethod"] if runtime else definition.calculation
        missing_views = sorted(set(required_views) - available_views)
        if runtime:
            pairs = list(zip(required_points, required_points[1:]))
            if runtime["closed"]:
                pairs.append((required_points[-1], required_points[0]))
            missing_landmarks = sorted({
                f"{view}:{point}"
                for (start, end), view in zip(pairs, runtime["segmentViews"])
                for point in (start, end)
                if point not in landmarks_by_view.get(view, set())
            })
        elif calculation == "manual_only":
            missing_landmarks = []
        else:
            missing_landmarks = sorted(set(required_points) - available_landmarks)
        missing_calibration = session["height_mm"] is None
        manual_required = calculation == "manual_only"
        status = ("manual_required" if manual_required else "ready_for_estimation"
                  if not missing_views and not missing_landmarks and not missing_calibration else "blocked")
        analyses.append({
            **definition_data, "requiredViews": required_views, "requiredLandmarks": required_points,
            "calculation": calculation, "status": status,
            "missingViews": missing_views, "missingLandmarks": missing_landmarks,
            "missingCalibration": missing_calibration,
            "message": "Enter a professional tape measurement; no automated path is published."
                if manual_required else "Required evidence is available; compute an estimate and send it for review."
                if status == "ready_for_estimation" else "Capture or view-specific landmark evidence is incomplete.",
        })
    return {
        "sessionId": session_id, "heightMm": float(session["height_mm"]) if session["height_mm"] else None,
        "availableViews": sorted(available_views), "availableLandmarks": sorted(available_landmarks),
        "availableLandmarksByView": {view: sorted(points) for view, points in landmarks_by_view.items()},
        "readyCount": sum(item["status"] == "ready_for_estimation" for item in analyses),
        "blockedCount": sum(item["status"] == "blocked" for item in analyses),
        "measurements": analyses,
    }
