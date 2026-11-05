import cv2
import numpy as np
import pytest

from app import main as main_module
from app import posture as posture_module
from app.posture import (
    Landmark,
    analyze_posture,
    estimate_pose,
    head_to_feet_completeness,
    posture_quality,
    view_orientation,
)


def lm(x, y, vis=1.0):
    return Landmark(x=x, y=y, visibility=vis)


def front_landmarks():
    return {
        "nose": lm(0.50, 0.10),
        "left_eye": lm(0.47, 0.09),
        "right_eye": lm(0.53, 0.09),
        "left_shoulder": lm(0.40, 0.28),
        "right_shoulder": lm(0.60, 0.28),
        "left_hip": lm(0.43, 0.55),
        "right_hip": lm(0.57, 0.55),
        "left_ankle": lm(0.45, 0.90),
        "right_ankle": lm(0.55, 0.90),
    }


def back_landmarks():
    pose = front_landmarks()
    # Back view: shoulders/hips still spread, but the face is not visible.
    for name in ("nose", "left_eye", "right_eye"):
        pose[name] = lm(pose[name].x, pose[name].y, vis=0.0)
    return pose


def side_landmarks():
    # Edge-on: shoulders collapse to a narrow spread; hips likewise.
    return {
        "left_shoulder": lm(0.47, 0.28),
        "right_shoulder": lm(0.50, 0.28),
        "left_hip": lm(0.48, 0.55),
        "right_hip": lm(0.50, 0.55),
        "nose": lm(0.49, 0.10),
        "left_eye": lm(0.48, 0.09),
        "right_eye": lm(0.50, 0.09),
        "left_ankle": lm(0.48, 0.90),
        "right_ankle": lm(0.50, 0.90),
    }


def test_front_orientation():
    assert view_orientation(front_landmarks()) == "front"


def test_back_orientation():
    assert view_orientation(back_landmarks()) == "back"


def test_side_orientation():
    assert view_orientation(side_landmarks()) == "side"


def test_back_orientation_via_depth_when_face_visibility_is_high():
    # MediaPipe can still report facial landmarks as "visible" from behind; the
    # depth signal (nose behind the torso) must win so back is not labelled front.
    pose = front_landmarks()
    pose["nose"] = Landmark(x=0.50, y=0.10, visibility=1.0, z=0.20)
    assert view_orientation(pose) == "back"


def test_front_orientation_via_depth_when_face_is_hidden():
    # Conversely, a forward-facing torso must not flip to "back" merely because
    # facial visibility dropped; the depth signal (nose in front) takes priority.
    pose = back_landmarks()
    pose["nose"] = Landmark(x=0.50, y=0.10, visibility=0.0, z=-0.20)
    assert view_orientation(pose) == "front"


def test_back_view_with_narrow_hips_is_still_back():
    # MediaPipe hip landmarks read narrower from behind (they follow the front iliac
    # crest), so a back view must not fall into 'unknown' when hip width is small.
    pose = front_landmarks()
    pose["left_hip"] = lm(0.48, 0.55)
    pose["right_hip"] = lm(0.52, 0.55)
    pose["nose"] = Landmark(x=0.50, y=0.10, visibility=1.0, z=0.20)
    assert view_orientation(pose) == "back"


def test_head_to_feet_pass():
    assert head_to_feet_completeness(front_landmarks())["status"] == "pass"


def test_head_to_feet_missing_feet():
    pose = front_landmarks()
    for name in ("left_ankle", "right_ankle"):
        pose[name] = lm(pose[name].x, pose[name].y, vis=0.0)
    assert head_to_feet_completeness(pose)["status"] == "fail"


def test_head_to_feet_clipped_head():
    pose = front_landmarks()
    pose["nose"] = lm(0.50, 0.005)
    pose["left_eye"] = lm(0.47, 0.004)
    pose["right_eye"] = lm(0.53, 0.004)
    assert head_to_feet_completeness(pose)["status"] == "fail"


def test_posture_pass():
    assert posture_quality(front_landmarks())["status"] == "pass"


def test_posture_tilted_shoulders():
    pose = front_landmarks()
    pose["left_shoulder"] = lm(0.40, 0.36)
    assert posture_quality(pose)["status"] == "fail"


def test_analyze_posture_front():
    result = analyze_posture(front_landmarks())
    assert result["orientation"] == "front"
    assert result["posture"] == "pass"
    assert result["headToFeet"] == "pass"


def test_estimate_pose_without_model_returns_none(monkeypatch):
    # Exercise the honest fallback: when the pose model is unavailable the
    # estimator returns None rather than inventing landmarks.
    monkeypatch.setattr(posture_module, "load_pose", lambda: None)
    image = np.zeros((200, 200, 3), np.uint8)
    assert estimate_pose(image) is None


def _make_video(tmp_path, frames=40):
    path = tmp_path / "turn.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (200, 200))
    assert writer.isOpened()
    for _ in range(frames):
        writer.write(np.full((200, 200, 3), 128, np.uint8))
    writer.release()
    return cv2.VideoCapture(str(path)), frames


def test_turn_coverage_unknown_without_model(monkeypatch, tmp_path):
    # MediaPipe is now installed in this environment, so exercise the honest
    # "no model" fallback explicitly by disabling the estimator.
    monkeypatch.setattr(main_module, "load_pose", lambda: None)
    monkeypatch.setattr(main_module, "estimate_pose", lambda frame, pose=None: None)
    reader, count = _make_video(tmp_path)
    try:
        coverage = main_module.turn_coverage(reader, count, count / 10.0)
    finally:
        reader.release()
    assert coverage["status"] == "unknown"
    assert coverage["method"] == "pose model unavailable"


def test_turn_coverage_complete(monkeypatch, tmp_path):
    poses = [front_landmarks(), side_landmarks(), back_landmarks()]
    state = {"i": 0}

    def fake_estimate(frame, pose=None):
        result = poses[state["i"] % len(poses)]
        state["i"] += 1
        return result

    monkeypatch.setattr(main_module, "load_pose", lambda: object())
    monkeypatch.setattr(main_module, "estimate_pose", fake_estimate)
    reader, count = _make_video(tmp_path)
    selected_frames = {}
    try:
        coverage = main_module.turn_coverage(reader, count, count / 10.0, selected_frames=selected_frames)
    finally:
        reader.release()
    assert coverage["status"] == "complete"
    assert set(coverage["seenViews"]) == {"front", "back", "side"}
    assert coverage["missingViews"] == []
    assert set(selected_frames) == {"front", "side", "back"}
    assert set(coverage["selectedViewFrames"]) == {"front", "side", "back"}


def test_turn_coverage_extracts_measurements_from_best_back_frame(monkeypatch, tmp_path):
    poses = [front_landmarks(), side_landmarks(), back_landmarks()]
    state = {"i": 0}

    def fake_estimate(frame, pose=None):
        result = poses[state["i"] % len(poses)]
        state["i"] += 1
        return result

    expected = {"status": "experimental", "measurements": [{"key": "across_back", "value": 40.0}]}
    monkeypatch.setattr(main_module, "load_pose", lambda: object())
    monkeypatch.setattr(main_module, "estimate_pose", fake_estimate)
    monkeypatch.setattr(main_module, "estimate_back_measurements", lambda frame, height, landmarks: dict(expected))
    reader, count = _make_video(tmp_path)
    try:
        coverage = main_module.turn_coverage(reader, count, count / 10.0, 1700)
    finally:
        reader.release()
    assert coverage["backMeasurements"]["measurements"][0]["key"] == "across_back"
    assert "timeSeconds" in coverage["backMeasurements"]


def test_turn_coverage_incomplete(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "load_pose", lambda: object())
    monkeypatch.setattr(main_module, "estimate_pose", lambda frame, pose=None: front_landmarks())
    reader, count = _make_video(tmp_path)
    try:
        coverage = main_module.turn_coverage(reader, count, count / 10.0)
    finally:
        reader.release()
    assert coverage["status"] == "incomplete"
    assert set(coverage["missingViews"]) == {"back", "side"}
