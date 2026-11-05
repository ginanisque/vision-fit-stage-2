"""Automatic posture, view orientation and head-to-feet completeness.

This module separates *analysis* (deterministic, tested with synthetic landmarks)
from *estimation* (a pluggable pose-landmark model). The analysis functions take
normalised landmark coordinates and never invent anatomical data: when no pose
model is available the estimator returns ``None`` and callers keep the honest
``unknown`` / ``review`` status used by VF-2.

Landmark names follow the 33-point MediaPipe Pose topology; any estimator that
yields the same named landmarks can drive the same analysis.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np

# MediaPipe Pose landmark indices (33-landmark topology), for documentation and
# for the optional estimator. Named keys are what analysis consumes.
POSE_LANDMARK_INDICES: dict[str, int] = {
    "nose": 0,
    "left_eye": 2,
    "right_eye": 5,
    "left_ear": 7,
    "right_ear": 8,
    "left_shoulder": 11,
    "right_shoulder": 12,
    "left_elbow": 13,
    "right_elbow": 14,
    "left_wrist": 15,
    "right_wrist": 16,
    "left_hip": 23,
    "right_hip": 24,
    "left_knee": 25,
    "right_knee": 26,
    "left_ankle": 27,
    "right_ankle": 28,
    "left_foot": 31,
    "right_foot": 32,
}

# Provisional thresholds. These are starting values only and are flagged as such
# in every recorded decision; they must be re-evaluated against real captures.
POSTURE_THRESHOLDS: dict[str, float] = {
    "minVisibility": 0.5,
    "headTopMargin": 0.02,
    "feetBottomMargin": 0.97,
    "shoulderLevelTolerance": 0.04,   # |dy| as a fraction of image height
    "hipLevelTolerance": 0.04,
    "torsoVerticalTolerance": 0.08,   # |dx| as a fraction of image width
    "minShoulderWidth": 0.15,         # fraction of image width for front/back
    "minHipWidth": 0.12,
    "maxSideShoulderWidth": 0.08,     # below this -> side view
}

# MediaPipe PoseLandmarker model. Downloaded from the official MediaPipe model
# bucket; not bundled with the repository. See ../models/ for the file.
POSE_MODEL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "models",
    "pose_landmarker_full.task",
)


@dataclass(frozen=True)
class Landmark:
    """A single landmark with normalised coordinates (0..1) relative to the image."""

    x: float
    y: float
    visibility: float = 0.0
    z: float = 0.0


def _visible(landmarks: dict[str, Landmark], *names: str) -> bool:
    return all(
        name in landmarks and landmarks[name].visibility >= POSTURE_THRESHOLDS["minVisibility"]
        for name in names
    )


def head_to_feet_completeness(landmarks: dict[str, Landmark]) -> dict:
    """Whether head and feet landmarks are present and not clipped by the frame."""
    head_present = _visible(landmarks, "nose") or _visible(landmarks, "left_eye", "right_eye")
    feet_present = _visible(landmarks, "left_ankle", "right_ankle") or _visible(
        landmarks, "left_foot", "right_foot"
    )
    if not head_present or not feet_present:
        return {
            "status": "fail",
            "reason": "Head and both feet must be visible; anatomical landmarks were not all detected.",
        }

    head_y = min(
        landmarks[n].y
        for n in ("nose", "left_eye", "right_eye")
        if n in landmarks and landmarks[n].visibility >= POSTURE_THRESHOLDS["minVisibility"]
    )
    feet_y = max(
        landmarks[n].y
        for n in ("left_ankle", "right_ankle", "left_foot", "right_foot")
        if n in landmarks and landmarks[n].visibility >= POSTURE_THRESHOLDS["minVisibility"]
    )
    if head_y < POSTURE_THRESHOLDS["headTopMargin"] or feet_y > POSTURE_THRESHOLDS["feetBottomMargin"]:
        return {
            "status": "fail",
            "reason": "Frame the whole body: keep space above the head and below the feet.",
        }
    return {"status": "pass", "reason": "Head and both feet are visible with clear margin."}


# Minimum |nose depth − torso depth| below which a frame is treated as ambiguous
# for front/back and the face-visibility fallback is used instead.
DEPTH_EPSILON = 0.03


def _facing(landmarks: dict[str, Landmark]) -> str:
    """Return ``front`` or ``back`` for a wide (non-side) pose.

    MediaPipe's ``z`` is relative depth (smaller = closer to the camera), so the
    nose sits clearly in front of the torso when facing the camera and behind it
    when facing away. This is more reliable than facial-landmark visibility, which
    the pose model can still report as high from behind; face visibility is kept
    only as a fallback when the depth signal is too small to be trusted.
    """
    torso_z = (
        landmarks["left_shoulder"].z
        + landmarks["right_shoulder"].z
        + landmarks["left_hip"].z
        + landmarks["right_hip"].z
    ) / 4.0
    nose = landmarks.get("nose")
    if nose is not None:
        if nose.z < torso_z - DEPTH_EPSILON:
            return "front"
        if nose.z > torso_z + DEPTH_EPSILON:
            return "back"
    return "front" if _visible(landmarks, "nose", "left_eye", "right_eye") else "back"


def view_orientation(landmarks: dict[str, Landmark]) -> str:
    """Classify a single frame as front, back, side or unknown from landmark geometry."""
    if not _visible(landmarks, "left_shoulder", "right_shoulder", "left_hip", "right_hip"):
        return "unknown"
    shoulder_width = abs(landmarks["left_shoulder"].x - landmarks["right_shoulder"].x)

    # Shoulder width is the reliable front/back-vs-side signal. Hip width is NOT
    # used as a hard gate because MediaPipe's hip landmarks (front iliac crest) read
    # noticeably narrower from behind, which would misclassify back views as unknown.
    if shoulder_width >= POSTURE_THRESHOLDS["minShoulderWidth"]:
        # Shoulders spread: facing toward or away from the camera.
        return _facing(landmarks)
    if shoulder_width <= POSTURE_THRESHOLDS["maxSideShoulderWidth"]:
        # Shoulders collapse to a narrow spread when the body is edge-on.
        return "side"
    return "unknown"


def posture_quality(landmarks: dict[str, Landmark]) -> dict:
    """Assess shoulder/hip levelness and vertical torso alignment."""
    required = ("left_shoulder", "right_shoulder", "left_hip", "right_hip")
    if not _visible(landmarks, *required):
        return {"status": "unknown", "reason": "Shoulders and hips must be detected to assess posture."}

    shoulder_tilt = abs(landmarks["left_shoulder"].y - landmarks["right_shoulder"].y)
    hip_tilt = abs(landmarks["left_hip"].y - landmarks["right_hip"].y)
    torso_drift = abs(
        (landmarks["left_shoulder"].x + landmarks["right_shoulder"].x) / 2
        - (landmarks["left_hip"].x + landmarks["right_hip"].x) / 2
    )
    head_above = all(
        landmarks[n].y < landmarks["left_shoulder"].y
        for n in ("nose", "left_eye", "right_eye")
        if n in landmarks and landmarks[n].visibility >= POSTURE_THRESHOLDS["minVisibility"]
    )

    problems = []
    if shoulder_tilt > POSTURE_THRESHOLDS["shoulderLevelTolerance"]:
        problems.append(f"shoulders are not level (tilt {shoulder_tilt:.3f})")
    if hip_tilt > POSTURE_THRESHOLDS["hipLevelTolerance"]:
        problems.append(f"hips are not level (tilt {hip_tilt:.3f})")
    if torso_drift > POSTURE_THRESHOLDS["torsoVerticalTolerance"]:
        problems.append(f"torso leans off vertical (drift {torso_drift:.3f})")
    if not head_above:
        problems.append("head is not above the shoulders")

    if problems:
        return {"status": "fail", "reason": "Adjust posture: " + "; ".join(problems) + "."}
    return {
        "status": "pass",
        "reason": "Shoulders and hips are level and the torso is upright.",
        "shoulderTilt": round(shoulder_tilt, 4),
        "hipTilt": round(hip_tilt, 4),
        "torsoDrift": round(torso_drift, 4),
    }


def analyze_posture(landmarks: dict[str, Landmark]) -> dict:
    """Run the three posture gates and return a combined, honest result."""
    completeness = head_to_feet_completeness(landmarks)
    orientation = view_orientation(landmarks)
    posture = posture_quality(landmarks)
    return {
        "headToFeet": completeness["status"],
        "orientation": orientation,
        "posture": posture["status"],
        "reasons": [completeness["reason"], posture["reason"]],
        "orientationMethod": "shoulder/hip landmark geometry",
    }


_pose_instance = None


def load_pose():
    """Return a cached MediaPipe PoseLandmarker, or ``None`` when unavailable.

    Uses the new ``mediapipe.tasks`` API (the legacy ``solutions`` API was removed
    in MediaPipe 1.1.0). The pose model is loaded once from ``POSE_MODEL_PATH`` and
    cached for the process lifetime; when MediaPipe or the model file is absent this
    returns ``None`` so callers keep the honest ``unknown`` / human-review status.
    """
    global _pose_instance
    if _pose_instance is not None:
        return _pose_instance
    try:
        from mediapipe.tasks import python as mp_python  # noqa: PLC0415
        from mediapipe.tasks.python import vision  # noqa: PLC0415

        if not os.path.exists(POSE_MODEL_PATH):
            return None
        options = vision.PoseLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=POSE_MODEL_PATH),
            running_mode=vision.RunningMode.IMAGE,
            num_poses=1,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        _pose_instance = vision.PoseLandmarker.create_from_options(options)
    except Exception:
        _pose_instance = None
    return _pose_instance


def estimate_pose(image_bgr: np.ndarray, pose=None) -> dict[str, Landmark] | None:
    """Return normalised named landmarks for a BGR image, or ``None``.

    ``pose`` may be a reusable :class:`~mediapipe.tasks.python.vision.PoseLandmarker`
    from :func:`load_pose` (which is cached and shared). This is deliberately lazy
    and tolerant: when the model is not installed (or fails), it returns ``None`` so
    callers fall back to the honest ``unknown`` / human-review status instead of
    inventing landmarks.
    """
    try:
        import cv2  # noqa: PLC0415
        import mediapipe as mp  # noqa: PLC0415

        if pose is None:
            pose = load_pose()
            if pose is None:
                return None
        rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB) if image_bgr.ndim == 3 else image_bgr
        result = pose.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
    except Exception:
        return None

    landmarks_list = getattr(result, "pose_landmarks", None)
    if not landmarks_list:
        return None
    raw = landmarks_list[0]

    landmarks: dict[str, Landmark] = {}
    for name, index in POSE_LANDMARK_INDICES.items():
        lm = raw[index]
        landmarks[name] = Landmark(
            x=float(lm.x),
            y=float(lm.y),
            visibility=float(getattr(lm, "visibility", 0.0)),
            z=float(getattr(lm, "z", 0.0)),
        )
    return landmarks


def landmarks_to_evidence(
    landmarks: dict[str, Landmark], width: int, height: int
) -> list[dict]:
    """Convert normalised landmarks into original-image coordinate evidence boxes."""
    evidence = []
    for name, lm in landmarks.items():
        if lm.visibility < POSTURE_THRESHOLDS["minVisibility"]:
            continue
        x = round(lm.x * width)
        y = round(lm.y * height)
        evidence.append(
            dict(
                kind="pose-landmark",
                label=f"pose landmark: {name}",
                box=dict(x=x, y=y, width=2, height=2),
            )
        )
    return evidence
