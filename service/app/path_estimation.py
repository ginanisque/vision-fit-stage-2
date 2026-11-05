"""Execute published measurement paths against tailoring keypoint predictions."""
from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np

from .circumference import _silhouette
from .posture import estimate_pose, load_pose


@dataclass(frozen=True)
class TailoringPoint:
    key: str
    x: float
    y: float
    confidence: float


POINT_NAME_FIELDS = ("class_name", "keypoint_class_name", "name", "label", "key")
CALIBRATION_REFERENCES = {
    "a4": (210.0, 297.0),
    "letter": (215.9, 279.4),
    "ruler_12in": (None, 304.8),
}


def _point_name(item: dict) -> str:
    name = next((str(item[field]) for field in POINT_NAME_FIELDS if item.get(field)), "")
    if name:
        return name
    if (
        item.get("class")
        and "class_id" in item
        and "width" not in item
        and "height" not in item
        and "keypoints" not in item
    ):
        return str(item["class"])
    return ""


def reference_scale_mm_per_pixel(image: np.ndarray, kind: str) -> tuple[float, dict]:
    """Detect a high-contrast rectangular reference and return its physical scale.

    Paper candidates must match their known aspect ratio. A 12-inch ruler only
    uses the long edge because ruler widths and printed markings are not standard.
    """
    dimensions = CALIBRATION_REFERENCES.get(kind)
    if dimensions is None:
        raise ValueError("Calibration reference must be A4, Letter, or a 1-foot ruler")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 45, 135)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8), iterations=2)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    image_area = float(image.shape[0] * image.shape[1])
    candidates: list[tuple[float, float, float, np.ndarray]] = []
    for contour in contours:
        area = float(cv2.contourArea(contour))
        if not image_area * .003 <= area <= image_area * .35:
            continue
        perimeter = cv2.arcLength(contour, True)
        polygon = cv2.approxPolyDP(contour, .025 * perimeter, True)
        if len(polygon) != 4 or not cv2.isContourConvex(polygon):
            continue
        rectangle = cv2.minAreaRect(contour)
        side_a, side_b = rectangle[1]
        short_px, long_px = sorted((float(side_a), float(side_b)))
        if short_px < 12 or long_px < 50:
            continue
        rectangularity = area / (short_px * long_px)
        if rectangularity < .78:
            continue
        ratio = long_px / short_px
        if kind == "ruler_12in":
            if ratio < 4.0:
                continue
            ratio_score = min(ratio / 8.0, 1.0)
        else:
            width_mm, height_mm = dimensions
            expected = max(width_mm, height_mm) / min(width_mm, height_mm)  # type: ignore[arg-type]
            ratio_error = abs(ratio - expected) / expected
            if ratio_error > .12:
                continue
            ratio_score = 1.0 - ratio_error
        candidates.append((area * rectangularity * ratio_score, short_px, long_px, polygon))
    if not candidates:
        raise ValueError("Calibration reference was not detected with credible rectangular geometry")
    _, short_px, long_px, polygon = max(candidates, key=lambda item: item[0])
    width_mm, height_mm = dimensions
    if kind == "ruler_12in":
        scale = float(height_mm) / long_px
    else:
        short_mm, long_mm = sorted((float(width_mm), float(height_mm)))
        short_scale, long_scale = short_mm / short_px, long_mm / long_px
        if abs(short_scale - long_scale) / ((short_scale + long_scale) / 2) > .12:
            raise ValueError("Calibration reference is tilted too far from the camera plane")
        scale = (short_scale + long_scale) / 2
    corners = [{"x": round(float(point[0][0]), 1), "y": round(float(point[0][1]), 1)} for point in polygon]
    return scale, {"kind": kind, "scaleMmPerPixel": round(scale, 6), "corners": corners}


def normalize_keypoints(payload: object, width: int, height: int) -> dict[str, TailoringPoint]:
    """Normalize one Roboflow person instance into pixel coordinates.

    Workflow responses may contain several people. Combining the highest-confidence
    point from every person creates a synthetic body, so select one complete,
    high-confidence instance before normalizing its keypoints.
    """
    found: dict[str, TailoringPoint] = {}

    def add(item: dict) -> None:
        name = _point_name(item)
        if not name or "x" not in item or "y" not in item:
            return
        try:
            x, y = float(item["x"]), float(item["y"])
            confidence = float(item.get("confidence", item.get("score", 1.0)))
        except (TypeError, ValueError):
            return
        if abs(x) <= 1 and abs(y) <= 1:
            x, y = x * width, y * height
        if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(confidence)):
            return
        if not (0 <= x <= width and 0 <= y <= height):
            return
        key = name.strip().lower().replace("-", " ").replace(" ", "_")
        point = TailoringPoint(key, x, y, max(0.0, min(1.0, confidence)))
        if key not in found or point.confidence > found[key].confidence:
            found[key] = point

    def walk(value: object) -> None:
        if isinstance(value, dict):
            add(value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    instances: list[tuple[tuple[int, float, float], object]] = []

    def find_instances(value: object) -> None:
        if isinstance(value, dict):
            keypoints = value.get("keypoints")
            if isinstance(keypoints, list):
                named = sum(
                    isinstance(item, dict)
                    and bool(_point_name(item))
                    and "x" in item and "y" in item
                    for item in keypoints
                )
                if named:
                    try:
                        confidence = float(value.get("confidence", value.get("score", 0.0)) or 0.0)
                        area = float(value.get("width", 0.0) or 0.0) * float(value.get("height", 0.0) or 0.0)
                    except (TypeError, ValueError):
                        confidence, area = 0.0, 0.0
                    instances.append(((named, confidence, area), keypoints))
                    return
            for child in value.values():
                find_instances(child)
        elif isinstance(value, list):
            for child in value:
                find_instances(child)

    find_instances(payload)
    if instances:
        walk(max(instances, key=lambda item: item[0])[1])
    else:
        walk(payload)
    return found


def view_scale_mm_per_pixel(image: np.ndarray, height_mm: float) -> float:
    """Use the body outline only to calibrate pixels; it is not a measurement path."""
    if not 1000 <= height_mm <= 2500:
        raise ValueError("Height must be between 1000 and 2500 mm")
    pose = load_pose()
    landmarks = estimate_pose(image, pose) if pose is not None else None
    if landmarks is None:
        raise ValueError("Full-body pose is required to calibrate keypoint distances")
    mask = _silhouette(image, landmarks)
    rows = np.flatnonzero(np.any(mask > 0, axis=1))
    if len(rows) < image.shape[0] * 0.35:
        raise ValueError("Body outline is too short for height calibration")
    return height_mm / float(rows[-1] - rows[0] + 1)


def calculate_ordered_path(
    definition: dict,
    points_by_view: dict[str, dict[str, TailoringPoint]],
    scales_by_view: dict[str, float],
) -> dict:
    points = list(definition["orderedPoints"])
    pairs = list(zip(points, points[1:]))
    if definition["closed"]:
        pairs.append((points[-1], points[0]))
    segments = []
    missing = []
    collapsed = []
    total_mm = 0.0
    segment_views = list(definition.get("segmentViews", []))
    if len(segment_views) != len(pairs):
        raise ValueError(f"{definition['measurementKey']} has an invalid segment-view mapping")
    for index, (start, end) in enumerate(pairs):
        required_view = segment_views[index]
        candidates = []
        for view in (required_view,):
            start_point = points_by_view.get(view, {}).get(start)
            end_point = points_by_view.get(view, {}).get(end)
            if start_point and end_point and view in scales_by_view:
                candidates.append((min(start_point.confidence, end_point.confidence), view, start_point, end_point))
        if not candidates:
            missing.append({"from": start, "to": end, "view": required_view})
            continue
        confidence, view, start_point, end_point = max(candidates, key=lambda item: item[0])
        pixel_length = math.hypot(end_point.x - start_point.x, end_point.y - start_point.y)
        if pixel_length <= 1.0:
            collapsed.append({"from": start, "to": end, "view": view})
            continue
        length_mm = pixel_length * scales_by_view[view]
        total_mm += length_mm
        segments.append({
            "from": start, "to": end, "view": view, "lengthMm": round(length_mm, 2),
            "confidence": round(confidence, 4),
            "fromPoint": {"x": round(start_point.x, 2), "y": round(start_point.y, 2)},
            "toPoint": {"x": round(end_point.x, 2), "y": round(end_point.y, 2)},
        })
    if missing:
        return {"key": definition["measurementKey"], "displayName": definition["displayName"],
                "status": "blocked", "missingSegments": missing, "segments": segments}
    if collapsed:
        return {"key": definition["measurementKey"], "displayName": definition["displayName"],
                "status": "blocked", "reason": "Collapsed keypoints cannot define a measurement path",
                "invalidSegments": collapsed, "segments": segments}
    if definition["closed"]:
        polygon = [points_by_view[view][name] for name, view in
                   zip(points, [segment_views[0], *segment_views[:-1]])]
        area = abs(sum(
            polygon[index].x * polygon[(index + 1) % len(polygon)].y
            - polygon[(index + 1) % len(polygon)].x * polygon[index].y
            for index in range(len(polygon))
        )) / 2
        if area <= 1.0:
            return {"key": definition["measurementKey"], "displayName": definition["displayName"],
                    "status": "blocked", "reason": "Collapsed keypoints cannot define a closed measurement path",
                    "invalidGeometry": True, "segments": segments}
    confidence = min(segment["confidence"] for segment in segments)
    return {
        "key": definition["measurementKey"], "displayName": definition["displayName"],
        "status": "estimated", "valueMm": round(total_mm, 2), "confidence": round(confidence, 4),
        "pathVersion": definition["version"], "pathVersionId": definition["id"],
        "pathType": definition["path"],
        "closed": definition["closed"], "orderedPoints": points, "segments": segments,
        "sourceViews": sorted({segment["view"] for segment in segments}),
    }
