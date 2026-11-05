import cv2
import numpy as np
import pytest

from app.path_estimation import calculate_ordered_path, normalize_keypoints, reference_scale_mm_per_pixel


@pytest.mark.parametrize(("kind", "width", "height"), [("a4", 210, 297), ("letter", 216, 279)])
def test_detects_paper_reference_scale(kind, width, height):
    image = np.zeros((600, 800, 3), np.uint8)
    cv2.rectangle(image, (100, 100), (100 + width, 100 + height), (255, 255, 255), -1)
    scale, evidence = reference_scale_mm_per_pixel(image, kind)
    assert scale == pytest.approx(1, abs=.03)
    assert evidence["kind"] == kind
    assert len(evidence["corners"]) == 4


def test_detects_ruler_from_outline_without_reading_marks():
    image = np.zeros((600, 800, 3), np.uint8)
    cv2.rectangle(image, (100, 200), (710, 250), (255, 255, 255), -1)
    scale, evidence = reference_scale_mm_per_pixel(image, "ruler_12in")
    assert scale == pytest.approx(.5, abs=.02)
    assert evidence["kind"] == "ruler_12in"


def test_rejects_unknown_or_missing_reference():
    image = np.zeros((600, 800, 3), np.uint8)
    with pytest.raises(ValueError, match="must be"):
        reference_scale_mm_per_pixel(image, "credit_card")
    with pytest.raises(ValueError, match="not detected"):
        reference_scale_mm_per_pixel(image, "a4")


def test_normalizes_nested_roboflow_keypoints():
    payload = {"predictions": [{"keypoints": [
        {"class_name": "bust_point_left", "x": 0.25, "y": 0.5, "confidence": 0.9},
        {"class_name": "bust_point_right", "x": 300, "y": 200, "confidence": 0.8},
    ]}]}
    points = normalize_keypoints(payload, 400, 600)
    assert points["bust_point_left"].x == 100
    assert points["bust_point_left"].y == 300
    assert points["bust_point_right"].x == 300


def test_normalizes_workflow_outputs_with_class_named_keypoints():
    payload = {"outputs": [
        {"predictions_at_0001": {"predictions": [{
            "confidence": 0.92,
            "keypoints": [
                {"class": "nape", "class_id": 0, "x": 120, "y": 40, "confidence": 0.9},
                {"class": "waist_center_back", "class_id": 1, "x": 125, "y": 260, "confidence": 0.85},
            ],
        }]}},
        {"predictions_at_040": {"predictions": []}},
    ]}

    points = normalize_keypoints(payload, 400, 600)

    assert set(points) == {"nape", "waist_center_back"}
    assert points["nape"].x == 120
    assert points["waist_center_back"].y == 260


def test_executes_closed_bust_path_in_published_order():
    names = ["bust_level_left_side", "bust_point_left", "bust_level_center_front",
             "bust_point_right", "bust_level_right_side", "bust_level_center_back"]
    front = normalize_keypoints([
        {"name": name, "x": index * 10, "y": 0 if index in (1, 2, 3) else 10, "confidence": .9}
        for index, name in enumerate(names[:-1])
    ], 100, 100)
    back = normalize_keypoints([
        {"name": "bust_level_right_side", "x": 40, "y": 10, "confidence": .8},
        {"name": "bust_level_center_back", "x": 25, "y": 20, "confidence": .8},
        {"name": "bust_level_left_side", "x": 0, "y": 10, "confidence": .8},
    ], 100, 100)
    result = calculate_ordered_path({
        "id": "bust-v2", "measurementKey": "bust", "displayName": "Bust", "version": 2,
        "path": "circumference", "closed": True, "orderedPoints": names,
        "segmentViews": ["front", "front", "front", "front", "back", "back"],
        "requiredViews": ["front", "back"],
    }, {"front": front, "back": back}, {"front": 2.0, "back": 2.0})
    assert result["status"] == "estimated"
    assert result["valueMm"] == pytest.approx(sum(item["lengthMm"] for item in result["segments"]), abs=0.02)
    assert [segment["view"] for segment in result["segments"]][-2:] == ["back", "back"]


def test_blocks_instead_of_inventing_a_missing_segment():
    points = normalize_keypoints([{"name": "a_point", "x": 0, "y": 0}], 100, 100)
    result = calculate_ordered_path({
        "id": "test-v1", "measurementKey": "test", "displayName": "Test", "version": 1,
        "path": "straight", "closed": False, "orderedPoints": ["a_point", "b_point"],
        "segmentViews": ["front"],
        "requiredViews": ["front"],
    }, {"front": points}, {"front": 1.0})
    assert result["status"] == "blocked"
    assert result["missingSegments"] == [{"from": "a_point", "to": "b_point", "view": "front"}]


def test_blocks_a_collapsed_keypoint_segment():
    points = normalize_keypoints([
        {"name": "a_point", "x": 40, "y": 40},
        {"name": "b_point", "x": 40, "y": 40},
    ], 100, 100)
    result = calculate_ordered_path({
        "id": "test-v1", "measurementKey": "test", "displayName": "Test",
        "path": "straight", "closed": False, "orderedPoints": ["a_point", "b_point"],
        "segmentViews": ["front"], "requiredViews": ["front"],
    }, {"front": points}, {"front": 1.0})
    assert result["status"] == "blocked"
    assert result["invalidSegments"] == [{"from": "a_point", "to": "b_point", "view": "front"}]


def test_blocks_a_collapsed_closed_path():
    points = normalize_keypoints([
        {"name": "point_a", "x": 10, "y": 10},
        {"name": "point_b", "x": 20, "y": 20},
        {"name": "point_c", "x": 30, "y": 30},
    ], 100, 100)
    result = calculate_ordered_path({
        "id": "test-v1", "measurementKey": "test", "displayName": "Test",
        "path": "circumference", "closed": True,
        "orderedPoints": ["point_a", "point_b", "point_c"],
        "segmentViews": ["front", "front", "front"], "requiredViews": ["front"],
    }, {"front": points}, {"front": 1.0})
    assert result["status"] == "blocked"
    assert result["invalidGeometry"] is True


def test_selects_one_person_instead_of_mixing_instances():
    payload = {"predictions": [
        {"confidence": .7, "width": 50, "height": 100, "keypoints": [
            {"name": "a_point", "x": 10, "y": 10, "confidence": .99},
        ]},
        {"confidence": .9, "width": 100, "height": 200, "keypoints": [
            {"name": "a_point", "x": 70, "y": 20, "confidence": .8},
            {"name": "b_point", "x": 90, "y": 20, "confidence": .8},
        ]},
    ]}
    points = normalize_keypoints(payload, 100, 200)
    assert set(points) == {"a_point", "b_point"}
    assert points["a_point"].x == 70
