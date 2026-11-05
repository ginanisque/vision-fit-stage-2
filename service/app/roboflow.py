"""Optional Roboflow Workflows boundary for measurement-oriented vision models.

This integration is deliberately disabled until the operator supplies workflow
IDs, an API key, and explicitly enables third-party processing. The current
OpenCV/MediaPipe capture checks remain the local baseline.
"""
from __future__ import annotations

import base64
import json
import os
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import cv2
import numpy as np

from .path_estimation import normalize_keypoints


def _collapsed_keypoint_output(output: object, image: bytes) -> bool:
    decoded = cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_COLOR)
    if decoded is None:
        return True
    points = normalize_keypoints(output, decoded.shape[1], decoded.shape[0])
    if len(points) < 2:
        return True
    xs = [point.x for point in points.values()]
    ys = [point.y for point in points.values()]
    spread = float(np.hypot(max(xs) - min(xs), max(ys) - min(ys)))
    return spread < max(4.0, min(decoded.shape[:2]) * 0.02)


def _truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def configuration_status() -> dict:
    workspace = os.getenv("ROBOFLOW_WORKSPACE", "").strip()
    keypoint = os.getenv("ROBOFLOW_KEYPOINT_WORKFLOW_ID", "").strip()
    segmentation = os.getenv("ROBOFLOW_SEGMENTATION_WORKFLOW_ID", "").strip()
    has_key = bool(os.getenv("ROBOFLOW_API_KEY", "").strip())
    enabled = _truthy("ROBOFLOW_ENABLED")
    placeholders = {
        "first-workflow-id", "second-workflow-id", "your-workflow-id",
        "keypoint-workflow-id", "segmentation-workflow-id",
    }
    keypoint_configured = bool(keypoint and keypoint.lower() not in placeholders)
    segmentation_configured = bool(segmentation and segmentation.lower() not in placeholders)
    keypoints_ready = bool(enabled and workspace and keypoint_configured and has_key)
    segmentation_ready = bool(enabled and workspace and segmentation_configured and has_key)
    configured = bool(workspace and keypoint_configured and has_key)
    placeholder_configured = bool(keypoint and not keypoint_configured)
    return {
        "enabled": enabled,
        "configured": configured,
        "provider": "roboflow_workflows",
        "keypointWorkflow": keypoint or None,
        "segmentationWorkflow": segmentation or None,
        "ready": enabled and configured,
        "keypointsReady": keypoints_ready,
        "segmentationReady": segmentation_ready,
        "reason": None if enabled and configured else (
            "Set ROBOFLOW_ENABLED=true after consent/privacy approval." if configured
            else "Replace the placeholder Roboflow keypoint workflow ID with the deployed workflow ID."
            if placeholder_configured
            else "Roboflow workspace, API key, and keypoint workflow ID are required."
        ),
    }


def _trim(value, depth: int = 0):
    """Keep structured predictions while refusing large rendered-image payloads."""
    if depth > 8:
        return "[nested output omitted]"
    if isinstance(value, dict):
        return {
            str(key): _trim(item, depth + 1)
            for key, item in value.items()
            if str(key).lower() not in {"image", "visualization", "output_image", "base64"}
        }
    if isinstance(value, list):
        return [_trim(item, depth + 1) for item in value[:500]]
    if isinstance(value, str) and len(value) > 4000:
        return value[:4000] + "…"
    return value


def _run_workflow(workflow_id: str, image: bytes) -> dict:
    workspace = os.environ["ROBOFLOW_WORKSPACE"].strip()
    api_key = os.environ["ROBOFLOW_API_KEY"].strip()
    endpoint = f"https://serverless.roboflow.com/{workspace}/workflows/{workflow_id}"
    payload = json.dumps({
        "api_key": api_key,
        "inputs": {"image": {"type": "base64", "value": base64.b64encode(image).decode("ascii")}},
    }).encode("utf-8")
    request = Request(endpoint, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=45) as response:
            return {"status": "complete", "output": _trim(json.load(response))}
    except HTTPError as error:
        detail = error.read(1000).decode("utf-8", "replace")
        return {"status": "failed", "error": f"Roboflow returned HTTP {error.code}: {detail}"}
    except (URLError, TimeoutError) as error:
        return {"status": "failed", "error": f"Roboflow request failed: {error}"}


def analyze_measurement_capture(image: bytes) -> dict:
    status = configuration_status()
    if not status["ready"]:
        return {**status, "status": "disabled"}
    workflows = {"keypoints": os.environ["ROBOFLOW_KEYPOINT_WORKFLOW_ID"].strip()}
    segmentation = os.getenv("ROBOFLOW_SEGMENTATION_WORKFLOW_ID", "").strip()
    if segmentation:
        workflows["segmentation"] = segmentation
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {name: executor.submit(_run_workflow, workflow, image) for name, workflow in workflows.items()}
        outputs = {name: future.result() for name, future in futures.items()}
    keypoints = outputs.get("keypoints")
    if keypoints and keypoints.get("status") == "complete" and _collapsed_keypoint_output(keypoints.get("output"), image):
        outputs["keypoints"] = {
            "status": "failed",
            "error": "Roboflow returned collapsed or insufficient named keypoints.",
        }
    return {
        **status,
        "status": "complete" if all(item["status"] == "complete" for item in outputs.values()) else "failed",
        "models": outputs,
    }


def analyze_keypoint_capture(image: bytes) -> dict:
    """Run only the tailoring-keypoint workflow used by ordered measurement paths."""
    status = configuration_status()
    if not status["keypointsReady"]:
        return {**status, "status": "disabled"}
    result = _run_workflow(os.environ["ROBOFLOW_KEYPOINT_WORKFLOW_ID"].strip(), image)
    if result.get("status") == "complete" and _collapsed_keypoint_output(result.get("output"), image):
        return {
            **status,
            "status": "failed",
            "error": "Roboflow returned collapsed or insufficient named keypoints; no measurements were produced.",
        }
    return {**status, **result}
