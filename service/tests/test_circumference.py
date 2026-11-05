import math

import pytest

import numpy as np

from app.circumference import (
    CORE_KEYS, _apply_profile, _arm_length_mm, _image_evidence, _side_waist_to_knee_mm,
    _width_at, ellipse_perimeter, estimate_back_measurements, estimate_circumferences,
)
from app.posture import Landmark


def test_ellipse_perimeter_is_circle_when_width_equals_depth():
    assert ellipse_perimeter(400, 400) == pytest.approx(math.pi * 400)


def test_ellipse_perimeter_uses_both_front_width_and_side_depth():
    result = ellipse_perimeter(400, 300)
    assert 1090 < result < 1110


def test_ellipse_perimeter_is_symmetric():
    assert ellipse_perimeter(420, 280) == pytest.approx(ellipse_perimeter(280, 420))


def test_straight_width_is_direction_independent_and_ignores_detached_arms():
    mask = np.zeros((40, 100), np.uint8)
    mask[18:23, 30:71] = 255
    mask[18:23, 5:16] = 255
    mask[18:23, 85:96] = 255
    left_to_right = _width_at(mask, 20, 50)
    right_to_left = abs((30 + left_to_right - 1) - 30) + 1
    assert left_to_right == right_to_left == 41


def test_vf3_covers_the_thirteen_core_registry_measurements():
    assert len(CORE_KEYS) == 13
    assert set(CORE_KEYS) == {
        "bust", "underbust", "bust_point", "bust_span", "bust_radius", "waist", "hip",
        "front_shoulder", "back_shoulder", "across_chest", "across_back",
        "nape_to_waist", "full_front_length",
    }


def test_versioned_profile_corrects_raw_geometry_and_exposes_mae():
    profile = {"factor": {"waist": 1.1}, "biasMm": {"waist": -20}, "maeMm": {"waist": 12}}
    value, mae = _apply_profile("waist", 800, profile, 45)
    assert value == pytest.approx(860)
    assert mae == 12


def test_profile_rejects_non_physical_corrections():
    with pytest.raises(ValueError, match="waist"):
        _apply_profile("waist", 800, {"factor": {"waist": -1}}, 45)


def test_arm_length_sums_native_shoulder_elbow_wrist_segments():
    landmarks = {
        "left_shoulder": Landmark(.2, .2, .9),
        "left_elbow": Landmark(.2, .4, .9),
        "left_wrist": Landmark(.2, .7, .9),
        "right_shoulder": Landmark(.8, .2, .8),
        "right_elbow": Landmark(.8, .4, .8),
        "right_wrist": Landmark(.8, .7, .8),
    }

    length_mm, confidence = _arm_length_mm(landmarks, (1000, 1000, 3), 2)

    assert length_mm == pytest.approx(1000)
    assert confidence == pytest.approx(.8)


def test_side_waist_to_knee_uses_pose_landmarks_and_height_scale():
    landmarks = {
        "left_shoulder": Landmark(.45, .2, .9),
        "right_shoulder": Landmark(.55, .2, .9),
        "left_hip": Landmark(.47, .5, .9),
        "right_hip": Landmark(.53, .5, .9),
        "left_knee": Landmark(.48, .8, .9),
        "right_knee": Landmark(.52, .8, .9),
    }

    length_mm, confidence = _side_waist_to_knee_mm(landmarks, (1000, 1000, 3), 1)

    assert length_mm == pytest.approx(390)
    assert confidence == pytest.approx(.9)


def test_video_estimator_adds_experimental_circumferences_and_lengths(monkeypatch):
    import app.circumference as circumference

    front = np.zeros((100, 100, 3), np.uint8)
    side = np.zeros_like(front)
    front_pose = {
        "left_shoulder": Landmark(.35, .2, .9), "right_shoulder": Landmark(.65, .2, .9),
        "left_hip": Landmark(.4, .7, .9), "right_hip": Landmark(.6, .7, .9),
    }
    side_pose = {
        "left_shoulder": Landmark(.49, .2, .9), "right_shoulder": Landmark(.51, .2, .9),
        "left_hip": Landmark(.49, .7, .9), "right_hip": Landmark(.51, .7, .9),
        "left_knee": Landmark(.49, .9, .9), "right_knee": Landmark(.51, .9, .9),
    }
    widths = {name: 20.0 for name in ("bust", "underbust", "waist", "hip", "across_chest")}
    monkeypatch.setattr(circumference, "load_pose", lambda: object())
    monkeypatch.setattr(
        circumference, "estimate_pose",
        lambda image, _pose: front_pose if image is front else side_pose,
    )
    monkeypatch.setattr(
        circumference, "view_orientation",
        lambda landmarks: "front" if landmarks is front_pose else "side",
    )
    monkeypatch.setattr(
        circumference, "_image_evidence",
        lambda *_args: (widths, {"across_chest": 35}, .9, 100.0),
    )
    monkeypatch.setattr(circumference, "_part_width", lambda *_args: (5.0, .9))
    monkeypatch.setattr(circumference, "_arm_length_mm", lambda *_args: (700.0, .9))
    monkeypatch.setattr(circumference, "_side_waist_to_knee_mm", lambda *_args: (450.0, .8))
    monkeypatch.setattr(circumference, "_load_calibration_profile", lambda: {
        "version": "test", "factor": {}, "biasMm": {}, "maeMm": {},
    })

    result = estimate_circumferences(front, side, 1700)
    measurements = {item["key"]: item for item in result["measurements"]}

    assert {"neck", "upper_arm", "thigh", "calf", "arm_length", "side_waist_to_knee"} <= measurements.keys()
    assert measurements["arm_length"]["value"] == pytest.approx(70)
    assert measurements["side_waist_to_knee"]["value"] == pytest.approx(45)
    assert all(measurements[key]["requiresReview"] for key in (
        "neck", "upper_arm", "thigh", "calf", "arm_length", "side_waist_to_knee",
    ))
    assert measurements["front_shoulder"]["displayName"] == "Shoulder width (left to right)"

    def missing_upper_arm(_image, _pose, key):
        if key == "upper_arm":
            raise ValueError("Upper arm is occluded")
        return 5.0, .9

    monkeypatch.setattr(circumference, "_part_width", missing_upper_arm)
    incomplete = estimate_circumferences(front, side, 1700)
    assert "upper_arm" not in {item["key"] for item in incomplete["measurements"]}
    assert {
        "key": "upper_arm",
        "displayName": "Upper arm circumference",
        "reason": "Upper arm is occluded",
    } in incomplete["unavailableMeasurements"]


def test_back_width_uses_pose_constrained_torso_instead_of_arm_extent(monkeypatch):
    import app.circumference as circumference

    image = np.zeros((100, 100, 3), np.uint8)
    silhouette = np.zeros((100, 100), np.uint8)
    silhouette[5:95, 39:62] = 255
    silhouette[34:37, 5:96] = 255
    landmarks = {
        "left_shoulder": Landmark(0.39, 0.25, 1.0),
        "right_shoulder": Landmark(0.61, 0.25, 1.0),
        "left_hip": Landmark(0.41, 0.65, 1.0),
        "right_hip": Landmark(0.59, 0.65, 1.0),
    }
    monkeypatch.setattr(circumference, "_silhouette", lambda *_args: silhouette)
    monkeypatch.setattr(circumference, "view_orientation", lambda _landmarks: "back")

    expected_widths, _, _, subject_height_px = _image_evidence(image, landmarks)
    result = estimate_back_measurements(image, 1800, landmarks)
    across_back = next(item for item in result["measurements"] if item["key"] == "across_back")
    arm_row = silhouette[35] > 0
    arm_extent_px = np.flatnonzero(arm_row)[-1] - np.flatnonzero(arm_row)[0] + 1
    unbounded_silhouette_width_cm = arm_extent_px * 1800 / subject_height_px / 10

    assert across_back["value"] == pytest.approx(expected_widths["across_chest"] * 1800 / subject_height_px / 10)
    assert across_back["value"] < unbounded_silhouette_width_cm
