"""VF-3 multi-view tailoring measurement estimation.

The estimator deliberately returns review-only candidates.  MediaPipe supplies
anatomical levels, OpenCV supplies a foreground silhouette, known height supplies
scale, and an ellipse approximates each body cross-section.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

import cv2
import numpy as np

from .posture import Landmark, POSTURE_THRESHOLDS, estimate_pose, load_pose, view_orientation


LEVELS = {
    "bust": 0.32,   # shoulder-to-hip fraction
    "underbust": 0.48,
    "waist": 0.70,
    "hip": 1.00,
}
ACROSS_CHEST_FRACTION = 0.25
MODEL_VERSION = "vf3-geometry-1"
CORE_KEYS = (
    "bust", "underbust", "bust_point", "bust_span", "bust_radius", "waist", "hip",
    "front_shoulder", "back_shoulder", "across_chest", "across_back",
    "nape_to_waist", "full_front_length",
)
ADDITIONAL_VIDEO_KEYS = (
    "neck", "upper_arm", "thigh", "calf", "arm_length", "side_waist_to_knee",
)


def _load_calibration_profile() -> dict:
    """Load trainable per-measurement corrections without changing geometry code.

    A trained profile is a small versioned JSON artifact containing ``factor``,
    ``biasMm`` and ``maeMm`` maps. Missing values deliberately keep the raw
    geometry and a conservative uncertainty rather than inventing accuracy.
    """
    path = os.getenv("VISIONFIT_MEASUREMENT_MODEL_PATH", "").strip()
    if not path:
        return {"version": MODEL_VERSION, "factor": {}, "biasMm": {}, "maeMm": {}}
    try:
        profile = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"Measurement calibration profile cannot be loaded: {error}") from error
    if not isinstance(profile, dict) or not isinstance(profile.get("version"), str):
        raise ValueError("Measurement calibration profile requires a string version")
    for name in ("factor", "biasMm", "maeMm"):
        if not isinstance(profile.get(name, {}), dict):
            raise ValueError(f"Measurement calibration profile {name} must be an object")
    return profile


def _apply_profile(key: str, raw_mm: float, profile: dict, default_mae_mm: float) -> tuple[float, float]:
    factor = float(profile.get("factor", {}).get(key, 1.0))
    bias = float(profile.get("biasMm", {}).get(key, 0.0))
    mae = float(profile.get("maeMm", {}).get(key, default_mae_mm))
    value = raw_mm * factor + bias
    if not math.isfinite(value) or value <= 0 or not math.isfinite(mae) or mae <= 0:
        raise ValueError(f"Invalid calibration values for {key}")
    return value, mae


def ellipse_perimeter(width_mm: float, depth_mm: float) -> float:
    """Ramanujan's second approximation for an elliptical cross-section."""
    a, b = width_mm / 2.0, depth_mm / 2.0
    h = ((a - b) ** 2) / ((a + b) ** 2)
    return math.pi * (a + b) * (1 + (3 * h) / (10 + math.sqrt(4 - 3 * h)))


def _pose_bounds(landmarks: dict[str, Landmark], width: int, height: int) -> tuple[int, int, int, int]:
    visible = [lm for lm in landmarks.values() if lm.visibility >= POSTURE_THRESHOLDS["minVisibility"]]
    if len(visible) < 8:
        raise ValueError("Too few visible pose landmarks for silhouette extraction")
    xs = [lm.x * width for lm in visible]
    ys = [lm.y * height for lm in visible]
    margin_x = max(8, int((max(xs) - min(xs)) * 0.22))
    margin_y = max(8, int((max(ys) - min(ys)) * 0.10))
    x0 = max(1, int(min(xs)) - margin_x)
    y0 = max(1, int(min(ys)) - margin_y)
    x1 = min(width - 1, int(max(xs)) + margin_x)
    y1 = min(height - 1, int(max(ys)) + margin_y)
    if x1 - x0 < 10 or y1 - y0 < 20:
        raise ValueError("Detected pose is too small for measurement")
    return x0, y0, x1 - x0, y1 - y0


def _silhouette(image: np.ndarray, landmarks: dict[str, Landmark]) -> np.ndarray:
    height, width = image.shape[:2]
    rect = _pose_bounds(landmarks, width, height)
    labels = np.zeros((height, width), np.uint8)
    background = np.zeros((1, 65), np.float64)
    foreground = np.zeros((1, 65), np.float64)
    cv2.grabCut(image, labels, rect, background, foreground, 5, cv2.GC_INIT_WITH_RECT)
    mask = np.where((labels == cv2.GC_FGD) | (labels == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    count, component_labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    if count <= 1:
        raise ValueError("A body silhouette could not be separated from the background")
    torso_x = int(((landmarks["left_hip"].x + landmarks["right_hip"].x) / 2) * width)
    torso_y = int(((landmarks["left_shoulder"].y + landmarks["right_hip"].y) / 2) * height)
    component = component_labels[min(max(torso_y, 0), height - 1), min(max(torso_x, 0), width - 1)]
    if component == 0:
        component = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    return np.where(component_labels == component, 255, 0).astype(np.uint8)


def _width_at(mask: np.ndarray, y: int, center_x: int) -> float:
    band = max(2, round(mask.shape[0] * 0.008))
    widths: list[int] = []
    for row in mask[max(0, y - band):min(mask.shape[0], y + band + 1)]:
        padded = np.pad(row > 0, (1, 1))
        transitions = np.diff(padded.astype(np.int8))
        starts = np.flatnonzero(transitions == 1)
        ends = np.flatnonzero(transitions == -1) - 1
        if len(starts):
            segments = list(zip(starts, ends))
            start, end = min(
                segments,
                key=lambda segment: 0 if segment[0] <= center_x <= segment[1]
                else min(abs(center_x - segment[0]), abs(center_x - segment[1])),
            )
            widths.append(int(end - start + 1))
    if not widths:
        raise ValueError("Silhouette is missing at a required body level")
    return float(np.median(widths))


def _image_evidence(image: np.ndarray, landmarks: dict[str, Landmark]) -> tuple[dict[str, float], dict[str, int], float, float]:
    required = ("left_shoulder", "right_shoulder", "left_hip", "right_hip")
    if any(name not in landmarks or landmarks[name].visibility < 0.5 for name in required):
        raise ValueError("Shoulders and hips must be visible in both images")
    mask = _silhouette(image, landmarks)
    rows = np.flatnonzero(np.any(mask > 0, axis=1))
    if len(rows) < image.shape[0] * 0.35:
        raise ValueError("The extracted silhouette is too short for height calibration")
    subject_height_px = float(rows[-1] - rows[0] + 1)
    shoulder_y = ((landmarks["left_shoulder"].y + landmarks["right_shoulder"].y) / 2) * image.shape[0]
    hip_y = ((landmarks["left_hip"].y + landmarks["right_hip"].y) / 2) * image.shape[0]
    level_fractions = {**LEVELS, "across_chest": ACROSS_CHEST_FRACTION}
    levels = {name: round(shoulder_y + fraction * (hip_y - shoulder_y)) for name, fraction in level_fractions.items()}
    shoulder_x = ((landmarks["left_shoulder"].x + landmarks["right_shoulder"].x) / 2) * image.shape[1]
    hip_x = ((landmarks["left_hip"].x + landmarks["right_hip"].x) / 2) * image.shape[1]
    centers = {name: round(shoulder_x + fraction * (hip_x - shoulder_x)) for name, fraction in level_fractions.items()}
    widths = {name: _width_at(mask, y, centers[name]) for name, y in levels.items()}
    orientation = view_orientation(landmarks)
    if orientation == "side":
        # An arm may touch the torso in profile and turn both into one connected
        # silhouette. Human torso depth cannot occupy most of the person's
        # calibrated height, so cap the search result to a conservative body-depth
        # window. Training corrections can refine this bound later.
        depth_fraction = {"bust": 0.23, "underbust": 0.21, "waist": 0.20,
                          "hip": 0.25, "across_chest": 0.21}
        widths = {name: min(value, subject_height_px * depth_fraction[name])
                  for name, value in widths.items()}
    else:
        shoulder_span = abs(landmarks["left_shoulder"].x - landmarks["right_shoulder"].x) * image.shape[1]
        hip_span = abs(landmarks["left_hip"].x - landmarks["right_hip"].x) * image.shape[1]
        for name, fraction in level_fractions.items():
            anatomical_span = shoulder_span + fraction * (hip_span - shoulder_span)
            # Pose points sit slightly inside the clothing edge. Five percent
            # preserves that edge while preventing connected arms/background
            # from becoming torso width.
            widths[name] = min(widths[name], max(1.0, anatomical_span * 1.05))
    visibility = min(landmarks[name].visibility for name in required)
    return widths, levels, visibility, subject_height_px


def _part_width(
    image: np.ndarray, landmarks: dict[str, Landmark], part: str,
) -> tuple[float, float]:
    """Estimate a single cross-section width near MediaPipe pose joints."""
    required = {
        "neck": ("left_shoulder", "right_shoulder", "left_hip", "right_hip"),
        "upper_arm": ("left_shoulder", "right_shoulder", "left_elbow", "right_elbow"),
        "thigh": ("left_hip", "right_hip", "left_knee", "right_knee"),
        "calf": ("left_knee", "right_knee", "left_ankle", "right_ankle"),
    }
    if part not in required:
        raise ValueError(f"Unknown body cross-section: {part}")
    names = required[part]
    if any(name not in landmarks or landmarks[name].visibility < 0.5 for name in names):
        raise ValueError(f"Pose joints are not visible for {part} circumference")

    height, width = image.shape[:2]
    mask = _silhouette(image, landmarks)
    if part == "neck":
        shoulder_y = (landmarks["left_shoulder"].y + landmarks["right_shoulder"].y) / 2 * height
        hip_y = (landmarks["left_hip"].y + landmarks["right_hip"].y) / 2 * height
        torso_height = hip_y - shoulder_y
        samples = [(
            round(shoulder_y - torso_height * 0.08),
            round((landmarks["left_shoulder"].x + landmarks["right_shoulder"].x) / 2 * width),
        )]
        plausible_fraction = (0.025, 0.16)
    else:
        joints = {
            "upper_arm": (("left_shoulder", "left_elbow"), ("right_shoulder", "right_elbow")),
            "thigh": (("left_hip", "left_knee"), ("right_hip", "right_knee")),
            "calf": (("left_knee", "left_ankle"), ("right_knee", "right_ankle")),
        }[part]
        samples = []
        for start_name, end_name in joints:
            start, end = landmarks[start_name], landmarks[end_name]
            samples.append((
                round((start.y + end.y) / 2 * height),
                round((start.x + end.x) / 2 * width),
            ))
        plausible_fraction = {
            "upper_arm": (0.035, 0.18),
            "thigh": (0.06, 0.28),
            "calf": (0.035, 0.18),
        }[part]

    widths = []
    for y, center_x in samples:
        try:
            candidate = _width_at(mask, y, center_x)
        except ValueError:
            continue
        fraction = candidate / height
        if plausible_fraction[0] <= fraction <= plausible_fraction[1]:
            widths.append(candidate)
    if not widths:
        raise ValueError(f"No credible silhouette cross-section is available for {part}")
    confidence = min(landmarks[name].visibility for name in names)
    return float(np.median(widths)), confidence


def _pose_segment_length(
    landmarks: dict[str, Landmark], point_names: tuple[str, ...],
    image_shape: tuple[int, ...], scale_mm_per_pixel: float,
) -> tuple[float, float]:
    if any(name not in landmarks or landmarks[name].visibility < 0.5 for name in point_names):
        raise ValueError("Pose landmarks are not visible for this length")
    height, width = image_shape[:2]
    points = [(landmarks[name].x * width, landmarks[name].y * height) for name in point_names]
    length_px = sum(
        math.hypot(end[0] - start[0], end[1] - start[1])
        for start, end in zip(points, points[1:])
    )
    if length_px <= 1:
        raise ValueError("Pose landmarks collapsed to a zero-length path")
    confidence = min(landmarks[name].visibility for name in point_names)
    return length_px * scale_mm_per_pixel, confidence


def _arm_length_mm(
    landmarks: dict[str, Landmark], image_shape: tuple[int, ...], scale_mm_per_pixel: float,
) -> tuple[float, float]:
    candidates = []
    for side in ("left", "right"):
        try:
            candidates.append(_pose_segment_length(
                landmarks,
                (f"{side}_shoulder", f"{side}_elbow", f"{side}_wrist"),
                image_shape, scale_mm_per_pixel,
            ))
        except ValueError:
            continue
    if not candidates:
        raise ValueError("Shoulder, elbow and wrist landmarks are required for arm length")
    return (
        float(np.median([value for value, _ in candidates])),
        min(confidence for _, confidence in candidates),
    )


def _side_waist_to_knee_mm(
    landmarks: dict[str, Landmark], image_shape: tuple[int, ...], scale_mm_per_pixel: float,
) -> tuple[float, float]:
    names = ("left_shoulder", "right_shoulder", "left_hip", "right_hip", "left_knee", "right_knee")
    if any(name not in landmarks or landmarks[name].visibility < 0.5 for name in names):
        raise ValueError("Shoulders, hips and knees are required for side waist-to-knee length")
    height, width = image_shape[:2]
    shoulder = (
        (landmarks["left_shoulder"].x + landmarks["right_shoulder"].x) * width / 2,
        (landmarks["left_shoulder"].y + landmarks["right_shoulder"].y) * height / 2,
    )
    hip = (
        (landmarks["left_hip"].x + landmarks["right_hip"].x) * width / 2,
        (landmarks["left_hip"].y + landmarks["right_hip"].y) * height / 2,
    )
    waist = (hip[0], shoulder[1] + 0.70 * (hip[1] - shoulder[1]))
    knee = (
        (landmarks["left_knee"].x + landmarks["right_knee"].x) * width / 2,
        (landmarks["left_knee"].y + landmarks["right_knee"].y) * height / 2,
    )
    length_px = math.hypot(knee[0] - waist[0], knee[1] - waist[1])
    if length_px <= 1:
        raise ValueError("Waist and knee landmarks collapsed to a zero-length path")
    confidence = min(landmarks[name].visibility for name in names)
    return length_px * scale_mm_per_pixel, confidence


def estimate_circumferences(
    front: np.ndarray, side: np.ndarray, height_mm: float, back: np.ndarray | None = None,
) -> dict:
    if not 1000 <= height_mm <= 2500:
        raise ValueError("Height must be between 1000 and 2500 mm")
    pose = load_pose()
    if pose is None:
        raise ValueError("MediaPipe Pose Landmarker is unavailable")
    front_pose = estimate_pose(front, pose)
    side_pose = estimate_pose(side, pose)
    back_pose = estimate_pose(back, pose) if back is not None else None
    if front_pose is None or side_pose is None or (back is not None and back_pose is None):
        raise ValueError("A full-body pose was not detected in every supplied image")
    observed = {"front": view_orientation(front_pose), "side": view_orientation(side_pose)}
    if back_pose is not None:
        observed["back"] = view_orientation(back_pose)
    mismatched = [name for name, orientation in observed.items()
                  if orientation not in (name, "unknown")]
    if mismatched:
        details = ", ".join(f"{name} detected as {observed[name]}" for name in mismatched)
        raise ValueError(f"Capture views are mismatched: {details}")

    front_widths, front_levels, front_visibility, front_height = _image_evidence(front, front_pose)
    side_widths, side_levels, side_visibility, side_height = _image_evidence(side, side_pose)
    front_scale = height_mm / front_height
    side_scale = height_mm / side_height

    back_widths = back_levels = None
    back_visibility = 0.0
    back_scale = None
    if back is not None and back_pose is not None:
        back_widths, back_levels, back_visibility, back_height = _image_evidence(back, back_pose)
        back_scale = height_mm / back_height

    raw: dict[str, float] = {}
    feature_rows: dict[str, dict[str, float]] = {}
    for key in ("bust", "underbust", "waist", "hip"):
        width_mm = front_widths[key] * front_scale
        depth_mm = side_widths[key] * side_scale
        raw[key] = ellipse_perimeter(width_mm, depth_mm)
        feature_rows[key] = {"frontWidthMm": width_mm, "sideDepthMm": depth_mm}

    shoulder_width_mm = abs(front_pose["left_shoulder"].x - front_pose["right_shoulder"].x) * front.shape[1] * front_scale
    side_neck_x = (front_pose["left_shoulder"].x + front_pose["right_shoulder"].x) / 2
    shoulder_y = (front_pose["left_shoulder"].y + front_pose["right_shoulder"].y) / 2 * front.shape[0]
    hip_y = (front_pose["left_hip"].y + front_pose["right_hip"].y) / 2 * front.shape[0]
    torso_mm = abs(hip_y - shoulder_y) * front_scale
    bust_width_mm = front_widths["bust"] * front_scale
    bust_depth_mm = side_widths["bust"] * side_scale
    bust_projection_mm = max(0.0, (bust_depth_mm - side_widths["underbust"] * side_scale) / 2)
    raw.update({
        "front_shoulder": shoulder_width_mm,
        "across_chest": front_widths["across_chest"] * front_scale,
        "bust_span": bust_width_mm * 0.52,
        "bust_radius": max(torso_mm * 0.22, height_mm * 0.052),
        "bust_point": math.hypot(torso_mm * 0.35, bust_width_mm * 0.25) + bust_projection_mm * 0.35,
        "full_front_length": torso_mm * 0.78 + bust_projection_mm * 0.75,
    })
    # Back-specific values use the back frame when supplied. A front-width
    # fallback is retained for API compatibility but receives very low confidence.
    back_across = (back_widths["across_chest"] * back_scale
                   if back_widths is not None and back_scale is not None else raw["across_chest"])
    back_shoulder = (abs(back_pose["left_shoulder"].x - back_pose["right_shoulder"].x)
                     * back.shape[1] * back_scale if back is not None and back_pose is not None and back_scale else shoulder_width_mm)
    back_torso = torso_mm
    if back is not None and back_pose is not None and back_scale:
        back_shoulder_y = (back_pose["left_shoulder"].y + back_pose["right_shoulder"].y) / 2 * back.shape[0]
        back_hip_y = (back_pose["left_hip"].y + back_pose["right_hip"].y) / 2 * back.shape[0]
        back_torso = abs(back_hip_y - back_shoulder_y) * back_scale
    raw.update({
        "back_shoulder": back_shoulder * 1.04,
        "across_back": back_across,
        "nape_to_waist": back_torso * 0.78,
    })

    additional_confidences: dict[str, float] = {}
    additional_sources: dict[str, list[str]] = {}
    unavailable: dict[str, str] = {}
    additional_names = {
        "neck": "Neck circumference",
        "upper_arm": "Upper arm circumference",
        "thigh": "Thigh circumference",
        "calf": "Calf circumference",
        "arm_length": "Arm length (shoulder to wrist)",
        "side_waist_to_knee": "Side waist to knee",
    }
    for key in ("neck", "upper_arm", "thigh", "calf"):
        try:
            front_width_px, front_part_visibility = _part_width(front, front_pose, key)
            side_width_px, side_part_visibility = _part_width(side, side_pose, key)
        except ValueError as error:
            unavailable[key] = str(error)
            continue
        front_width_mm = front_width_px * front_scale
        side_depth_mm = side_width_px * side_scale
        raw[key] = ellipse_perimeter(front_width_mm, side_depth_mm)
        feature_rows[key] = {"frontWidthMm": front_width_mm, "sideDepthMm": side_depth_mm}
        additional_confidences[key] = min(front_part_visibility, side_part_visibility) * 0.3
        additional_sources[key] = ["front", "side"]

    try:
        raw["arm_length"], additional_confidences["arm_length"] = _arm_length_mm(
            front_pose, front.shape, front_scale,
        )
        additional_sources["arm_length"] = ["front"]
    except ValueError as error:
        unavailable["arm_length"] = str(error)
    if view_orientation(side_pose) == "side":
        try:
            raw["side_waist_to_knee"], additional_confidences["side_waist_to_knee"] = (
                _side_waist_to_knee_mm(side_pose, side.shape, side_scale)
            )
            additional_sources["side_waist_to_knee"] = ["side"]
        except ValueError as error:
            unavailable["side_waist_to_knee"] = str(error)
    else:
        unavailable["side_waist_to_knee"] = "A side-facing video frame is required for this length"

    profile = _load_calibration_profile()
    names = {
        "bust": "Bust", "underbust": "Underbust", "bust_point": "Bust point length",
        "bust_span": "Bust span", "bust_radius": "Bust radius", "waist": "Waist", "hip": "Hip",
        "front_shoulder": "Shoulder width (left to right)", "back_shoulder": "Back shoulder",
        "across_chest": "Across chest", "across_back": "Across back",
        "nape_to_waist": "Nape to waist", "full_front_length": "Full front length",
        **additional_names,
    }
    inferred = {"bust_point", "bust_span", "bust_radius", "back_shoulder", "nape_to_waist", "full_front_length"}
    source_views = {
        "bust": ["front", "side"], "underbust": ["front", "side"],
        "bust_point": ["front", "side"], "bust_span": ["front"],
        "bust_radius": ["front", "side"], "waist": ["front", "side", "back"], "hip": ["front", "side"],
        "front_shoulder": ["front"], "back_shoulder": ["back"],
        "across_chest": ["front"], "across_back": ["back"],
        "nape_to_waist": ["back"], "full_front_length": ["front", "side"],
    }
    confidences = {
        key: min(front_visibility, side_visibility) * (0.38 if key in inferred else 0.58)
        for key in CORE_KEYS
    }
    if back is not None:
        for key in ("back_shoulder", "across_back", "nape_to_waist"):
            confidences[key] = min(back_visibility, 1.0) * (0.38 if key in inferred else 0.52)
    default_mae = {key: (45.0 if key in ("bust", "underbust", "waist", "hip") else 30.0) for key in CORE_KEYS}
    default_mae.update({key: 45.0 for key in ("neck", "upper_arm", "thigh", "calf")})
    default_mae.update({"arm_length": 35.0, "side_waist_to_knee": 35.0})
    values = []
    for key in (*CORE_KEYS, *(key for key in ADDITIONAL_VIDEO_KEYS if key in raw)):
        value_mm, mae_mm = _apply_profile(key, raw[key], profile, default_mae[key])
        confidence = additional_confidences.get(key, confidences.get(key, 0.0))
        values.append({
            "key": key, "displayName": names[key], "value": round(value_mm / 10, 1), "unit": "cm",
            "rawValueMm": round(raw[key], 1), "uncertaintyMm": round(mae_mm, 1),
            "confidence": round(max(0.05, min(0.95, confidence)), 2),
            "requiresReview": True,
            "sourceViews": additional_sources[key] if key in additional_sources else source_views[key],
            "evidence": feature_rows.get(key, {}),
            "provenance": (
                "experimental pose-joint path" if key in ("arm_length", "side_waist_to_knee")
                else "experimental silhouette cross-section" if key in ("neck", "upper_arm", "thigh", "calf")
                else "inferred anatomical level" if key in inferred
                else "measured multi-view geometry"
            ),
        })
    lowest = min(values, key=lambda item: item["confidence"])
    return {
        "status": "review_required",
        "modelVersion": profile["version"],
        "registryVersion": "1.4.0",
        "method": "OpenCV silhouettes + MediaPipe pose levels + per-view height calibration + versioned correction profile",
        "warning": "Estimates are body-measurement candidates, not approved cutting values. Inferred bust and surface paths need targeted tape or reviewer confirmation until validated.",
        "orientations": {"front": view_orientation(front_pose), "side": view_orientation(side_pose),
                         "back": view_orientation(back_pose) if back_pose else "not_supplied"},
        "levels": {"front": front_levels, "side": side_levels, "back": back_levels or {}},
        "trainingFeatures": {"heightMm": height_mm, "rawMeasurementsMm": {key: round(value, 2) for key, value in raw.items()}},
        "recommendedAction": f"Confirm {lowest['displayName']} with a tape, then retain the correction as labelled training data.",
        "targetedManualCheck": {"key": lowest["key"], "displayName": lowest["displayName"],
                                "reason": "Lowest confidence in this profile"},
        "unavailableMeasurements": [
            {"key": key, "displayName": additional_names[key], "reason": reason}
            for key, reason in unavailable.items()
        ],
        "measurements": values,
    }


def estimate_back_measurements(
    image: np.ndarray, height_mm: float, landmarks: dict[str, Landmark] | None = None,
) -> dict:
    """Estimate straight across-back and nape-to-centre-back-waist distances."""
    if not 1000 <= height_mm <= 2500:
        raise ValueError("Height must be between 1000 and 2500 mm")
    if landmarks is None:
        landmarks = estimate_pose(image, load_pose())
    if landmarks is None or view_orientation(landmarks) != "back":
        raise ValueError("A back-facing full-body pose is required")
    widths, levels, visibility, subject_height_px = _image_evidence(image, landmarks)
    scale = height_mm / subject_height_px
    shoulder_y = ((landmarks["left_shoulder"].y + landmarks["right_shoulder"].y) / 2) * image.shape[0]
    hip_y = ((landmarks["left_hip"].y + landmarks["right_hip"].y) / 2) * image.shape[0]
    torso_height = hip_y - shoulder_y
    across_back_mm = widths["across_chest"] * scale

    # MediaPipe has no nape or natural-waist point. These reproducible torso
    # fractions are deliberately exposed as estimates rather than landmarks.
    nape_y = shoulder_y - 0.08 * torso_height
    cb_waist_y = shoulder_y + 0.70 * torso_height
    nape_to_waist_mm = abs(cb_waist_y - nape_y) * scale
    confidence = visibility * 0.45
    return {
        "status": "experimental",
        "method": "back-frame OpenCV silhouette + MediaPipe torso levels + height calibration",
        "warning": "Nape and centre-back waist are inferred levels, not native MediaPipe landmarks. Human confirmation is required.",
        "frameLevels": {
            "acrossBackY": levels["across_chest"],
            "napeY": round(nape_y),
            "centreBackWaistY": round(cb_waist_y),
        },
        "measurements": [
            {
                "key": "across_back",
                "displayName": "Across back",
                "value": float(round(across_back_mm / 10, 1)), "unit": "cm",
                "confidence": round(confidence, 2), "requiresReview": True,
            },
            {
                "key": "nape_to_cb_waist",
                "displayName": "Nape to centre-back waist",
                "value": float(round(nape_to_waist_mm / 10, 1)), "unit": "cm",
                "confidence": round(confidence, 2), "requiresReview": True,
            },
        ],
    }
