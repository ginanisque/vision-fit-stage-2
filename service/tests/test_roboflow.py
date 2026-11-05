from app.roboflow import configuration_status
import cv2
import numpy as np


def test_placeholder_workflow_is_not_reported_as_configured(monkeypatch):
    monkeypatch.setenv("ROBOFLOW_ENABLED", "true")
    monkeypatch.setenv("ROBOFLOW_WORKSPACE", "visionfit")
    monkeypatch.setenv("ROBOFLOW_API_KEY", "test-key")
    monkeypatch.setenv("ROBOFLOW_KEYPOINT_WORKFLOW_ID", "first-workflow-id")

    status = configuration_status()

    assert status["configured"] is False
    assert status["ready"] is False
    assert "placeholder" in status["reason"].lower()


def test_collapsed_roboflow_keypoints_fail_closed(monkeypatch):
    import app.roboflow as roboflow

    monkeypatch.setenv("ROBOFLOW_ENABLED", "true")
    monkeypatch.setenv("ROBOFLOW_WORKSPACE", "visionfit")
    monkeypatch.setenv("ROBOFLOW_API_KEY", "test-key")
    monkeypatch.setenv("ROBOFLOW_KEYPOINT_WORKFLOW_ID", "deployed-workflow")
    image = cv2.imencode(".png", np.zeros((300, 400, 3), np.uint8))[1].tobytes()
    monkeypatch.setattr(roboflow, "_run_workflow", lambda *_args: {
        "status": "complete",
        "output": [{"name": name, "x": 180, "y": 120, "confidence": .99}
                   for name in ("left_shoulder", "right_shoulder", "left_hip", "right_hip")],
    })

    result = roboflow.analyze_keypoint_capture(image)

    assert result["status"] == "failed"
    assert "collapsed" in result["error"]
    assert "output" not in result


def test_spatially_distinct_roboflow_keypoints_are_preserved(monkeypatch):
    import app.roboflow as roboflow

    monkeypatch.setenv("ROBOFLOW_ENABLED", "true")
    monkeypatch.setenv("ROBOFLOW_WORKSPACE", "visionfit")
    monkeypatch.setenv("ROBOFLOW_API_KEY", "test-key")
    monkeypatch.setenv("ROBOFLOW_KEYPOINT_WORKFLOW_ID", "deployed-workflow")
    image = cv2.imencode(".png", np.zeros((300, 400, 3), np.uint8))[1].tobytes()
    output = [{"name": name, "x": x, "y": y, "confidence": .9} for name, x, y in (
        ("left_shoulder", 100, 80), ("right_shoulder", 300, 80),
        ("left_hip", 125, 220), ("right_hip", 275, 220),
    )]
    monkeypatch.setattr(roboflow, "_run_workflow", lambda *_args: {"status": "complete", "output": output})

    result = roboflow.analyze_keypoint_capture(image)

    assert result["status"] == "complete"
    assert result["output"] == output
