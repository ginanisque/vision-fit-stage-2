import cv2
import numpy as np
import pytest
from uuid import uuid4
from fastapi.testclient import TestClient
from app.capture import capture_decision
from app.auth import SessionUser, current_user
from app.main import app


@pytest.fixture(autouse=True)
def authenticated_capture(monkeypatch):
    import app.main as main_module
    user = SessionUser(id=uuid4(), auth_subject="test-subject", email="customer@example.test", role="customer")
    app.dependency_overrides[current_user] = lambda: user
    session_id = str(uuid4())
    monkeypatch.setattr(main_module, "ensure_session", lambda *_args, **_kwargs: session_id)
    monkeypatch.setattr(main_module, "persist_analysis", lambda **_kwargs: {
        "captureSessionId": session_id, "assetId": str(uuid4()), "analysisRunId": str(uuid4())
    })
    yield
    app.dependency_overrides.clear()


def subject(cord=True, clipped=False, duplicate=False):
    image = np.full((600,400,3),180,np.uint8)
    y = 0 if clipped else 45
    image[y:555,120:280] = np.random.default_rng(12).integers(65,105,(555-y,160,1),dtype=np.uint8)
    if cord: image[290:298,120:280] = (30,220,30)
    if duplicate: image[260:268,120:280] = (30,220,30)
    return image


def encoded(image): return cv2.imencode('.png',image)[1].tobytes()


def test_candidate_requires_review():
    image = subject()
    r = capture_decision('front',image,encoded(image))
    assert r['decision'] == 'review'
    assert r['captureChecks']['waistCord']['status'] == 'candidate'
    assert r['captureChecks']['posture']['status'] == 'unknown'
    assert r['captureChecks']['framing']['status'] == 'pass'
    assert {e['kind'] for e in r['evidence']} == {'subject-candidate','cord-candidate'}


@pytest.mark.parametrize('options,status', [({'cord':False},'missing'),({'duplicate':True},'ambiguous')])
def test_cord_failure_changes_action(options,status):
    image = subject(**options)
    r = capture_decision('side',image,encoded(image))
    assert r['decision'] == 'recapture'
    assert r['captureChecks']['waistCord']['status'] == status


def test_clipped_framing():
    image = subject(clipped=True)
    r = capture_decision('front',image,encoded(image))
    assert r['decision'] == 'recapture'
    assert r['captureChecks']['framing']['status'] == 'fail'


def test_no_subject_never_proceeds():
    image = np.full((600,400,3),180,np.uint8)
    r = capture_decision('front',image,encoded(image))
    assert r['decision'] != 'proceed'
    assert not r['evidence']


def test_original_coordinates():
    image = cv2.resize(subject(),(1200,1800))
    r = capture_decision('front',image,encoded(image))
    assert 350 <= r['evidence'][0]['box']['x'] <= 370
    assert r['evidence'][0]['box']['width'] > 470


@pytest.mark.parametrize('endpoint',['/api/capture','/api/turn-video'])
def test_consent(endpoint):
    with TestClient(app) as c:
        assert c.post(endpoint,data={'view':'front'},files={'file':('photo.png',encoded(subject()))}).status_code == 403


def test_capture_is_recorded():
    with TestClient(app) as c:
        r = c.post('/api/capture',data={'view':'front','consent':'true'},files={'file':('photo.png',encoded(subject()))})
        assert r.status_code == 200
        assert r.json()['decision'] == 'review'
        assert r.json()['analysisRunId']


def test_still_capture_is_reference_only_even_with_legacy_provider_consent(monkeypatch):
    import app.main as main_module
    monkeypatch.setattr(main_module, "capture_decision", lambda view, image, _data: {
        "id": "capture-test", "view": view, "decision": "review",
        "dimensions": {"width": image.shape[1], "height": image.shape[0]},
        "evidence": [], "reasons": [],
    })
    with TestClient(app) as c:
        response = c.post(
            "/api/capture",
            data={"view": "front", "consent": "true", "external_vision_consent": "true"},
            files={"file": ("photo.png", encoded(subject()))},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["measurementVision"]["status"] == "reference_only"
    assert not any(item["kind"] == "tailoring-keypoint" for item in body["evidence"])


def test_capture_batch_uses_one_session_for_all_views(monkeypatch):
    import app.main as main_module
    monkeypatch.setattr(main_module, 'capture_decision', lambda view, image, _data: {
        'id': f'{view}-test', 'view': view, 'decision': 'review',
        'dimensions': {'width': image.shape[1], 'height': image.shape[0]},
        'evidence': [], 'reasons': [],
    })
    image = encoded(subject())
    with TestClient(app) as c:
        r = c.post('/api/captures', data={'consent': 'true', 'height_mm': '1650'}, files={
            'front': ('front.png', image), 'side': ('side.png', image), 'back': ('back.png', image),
        })
    assert r.status_code == 200
    body = r.json()
    assert len(body['results']) == 3
    assert [item['view'] for item in body['results']] == ['front', 'side', 'back']
    assert {item['captureSessionId'] for item in body['results']} == {body['captureSessionId']}
    assert all(item['measurementVision']['status'] == 'reference_only' for item in body['results'])


def test_still_image_estimate_endpoint_is_gone():
    with TestClient(app) as c:
        response = c.post('/api/measurement-estimates')
    assert response.status_code == 410
    assert "slow-turn video" in response.json()["detail"]


def test_bad_video():
    with TestClient(app) as c:
        assert c.post('/api/turn-video',data={'consent':'true'},files={'file':('bad.webm',b'bad')}).status_code == 400


@pytest.mark.parametrize('seconds,dark,decision',[(10,False,'review'),(2,True,'review')])
def test_video_quality_and_duration(tmp_path,seconds,dark,decision,monkeypatch):
    # Isolate duration/quality: disable the pose model so turn coverage stays
    # 'unknown' (coverage is tested separately in test_posture.py).
    import app.main as main_module
    monkeypatch.setattr(main_module, 'load_pose', lambda: None)
    monkeypatch.setattr(main_module, 'estimate_pose', lambda frame, pose=None: None)

    path = tmp_path/'turn.avi'
    writer = cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'MJPG'),10,(400,600))
    assert writer.isOpened()
    for _ in range(seconds*10): writer.write(np.zeros((600,400,3),np.uint8) if dark else subject())
    writer.release()
    with TestClient(app) as c:
        r = c.post('/api/turn-video',data={'consent':'true'},files={'file':('turn.avi',path.read_bytes())})
        assert r.status_code == 200
        assert r.json()['durationSeconds'] == seconds
        assert len(r.json()['samples']) == 5
        assert r.json()['decision'] == decision


def test_longer_video_is_sampled_not_penalized_for_duration(tmp_path, monkeypatch):
    # A user should not need to time a slow turn precisely: a longer clip with good
    # frames is sampled across the whole turn and stays 'review' rather than being
    # rejected or marked 'recapture' for its length.
    import app.main as main_module
    monkeypatch.setattr(main_module, 'load_pose', lambda: None)
    monkeypatch.setattr(main_module, 'estimate_pose', lambda frame, pose=None: None)

    seconds = 30
    path = tmp_path/'turn.avi'
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'), 10, (400, 600))
    assert writer.isOpened()
    for _ in range(seconds * 10):
        writer.write(subject())
    writer.release()
    with TestClient(app) as c:
        r = c.post('/api/turn-video', data={'consent': 'true'}, files={'file': ('turn.avi', path.read_bytes())})
        assert r.status_code == 200
        assert r.json()['durationSeconds'] == seconds
        assert r.json()['decision'] == 'review'


def test_complete_video_saves_review_only_measurements(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import app.main as main_module

    orientations = ["front", "side", "back"]
    state = {"index": 0}

    def next_orientation(_landmarks):
        orientation = orientations[state["index"] % len(orientations)]
        state["index"] += 1
        return orientation

    landmarks = {
        name: SimpleNamespace(visibility=0.95)
        for name in ("left_shoulder", "right_shoulder", "left_hip", "right_hip")
    }
    monkeypatch.setattr(main_module, "load_pose", lambda: object())
    monkeypatch.setattr(main_module, "estimate_pose", lambda _frame, _pose=None: landmarks)
    monkeypatch.setattr(main_module, "view_orientation", next_orientation)
    monkeypatch.setattr(
        main_module, "estimate_back_measurements",
        lambda *_args: {"status": "experimental", "measurements": []},
    )
    geometry = {
        "modelVersion": "vf3-test",
        "measurements": [{
            "key": "bust", "displayName": "Bust", "value": 90.0, "unit": "cm",
            "rawValueMm": 900.0, "confidence": 0.5, "sourceViews": ["front", "side"],
        }],
    }
    monkeypatch.setattr(main_module, "estimate_circumferences", lambda *_args: geometry)
    monkeypatch.setattr(
        main_module, "reference_scale_mm_per_pixel",
        lambda *_args: (2.0, {"kind": "a4", "scaleMmPerPixel": 2.0, "corners": []}),
    )
    monkeypatch.setattr(main_module, "view_scale_mm_per_pixel", lambda *_args: 2.05)
    saved = {}
    session_arguments = {}
    monkeypatch.setattr(main_module, "ensure_session", lambda *args: (
        session_arguments.update({"args": args}) or uuid4()
    ))
    monkeypatch.setattr(main_module, "persist_video_estimates", lambda **kwargs: (
        saved.update(kwargs) or {
            "measurementTableId": "table-1", "persistedKeys": ["bust"], "skippedKeys": [],
        }
    ))

    path = tmp_path / "turn.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (400, 600))
    assert writer.isOpened()
    for _ in range(100):
        writer.write(subject())
    writer.release()

    with TestClient(app) as client:
        response = client.post(
            "/api/turn-video",
            data={
                "consent": "true", "height_mm": "1700", "session_id": str(uuid4()),
                "training_consent": "true", "calibration_kind": "a4",
            },
            files={
                "file": ("turn.avi", path.read_bytes(), "video/x-msvideo"),
                "calibration_reference": ("reference.png", encoded(subject()), "image/png"),
            },
        )

    assert response.status_code == 200
    result = response.json()
    assert result["turnCoverage"]["selectedViewFrames"].keys() == {"front", "side", "back"}
    assert result["measurementEstimates"]["persistedKeys"] == ["bust"]
    assert result["measurementEstimates"]["measurements"][0]["requiresReview"] is True
    assert result["calibration"]["status"] == "accepted"
    assert result["calibration"]["disagreementPercent"] == 2.4
    assert saved["estimates"][0]["valueMm"] == 900.0
    assert session_arguments["args"][2:] == (1700.0, True)
