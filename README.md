# Ginani VisionFit — ordered-keypoint measurement runtime

VisionFit executes versioned, administrator-published paths made from the exact COCO v6 tailoring
keypoint names. Consecutive points form measured segments; circumference paths close from the last
point back to the first. Body-outline masks support capture checks and per-view scale calibration
only. They are not measurement points. Missing keypoints block the affected measurement for review.

The first working VisionFit milestone: a standalone, local capture-guidance interface plus a
Python service with **pinned OpenCV 5** that runs a real exposure/blur quality check and returns
a recorded `recapture` / `proceed` decision.

```
visionfit/
  frontend/   React + TypeScript + Vite capture wizard
  service/    Python + FastAPI + OpenCV 5 quality service
```

See `../VISIONFIT_CHECKLIST.md` for the full milestone plan and `../spec.md` /
`../PROJECT_STATE.md` for the current direction.

## Prerequisites

- Node 22 + npm 10 (present).
- Python 3.12 (present). The system image lacks `python3-venv`; the service setup below
  bootstraps pip from the official installer.

## 1. Run the quality service

```bash
cd visionfit/service

# one-time setup (venv already created here; repeat if re-cloning elsewhere)
python3 -m venv --without-pip .venv
curl -sSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
./.venv/bin/python /tmp/get-pip.py --quiet
./.venv/bin/python -m pip install -r requirements.txt

# start
./.venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

Verify OpenCV 5: `./.venv/bin/python -c "import cv2; print(cv2.__version__)"` → `5.0.0`.

Endpoints:

- `GET  /api/health`
- `POST /api/quality` — form fields `view` (`front`|`side`) + `file`
- `GET  /api/decisions`

## 2. Run the frontend

```bash
cd visionfit/frontend
npm install
npm run dev      # http://localhost:5173 (proxies /api to :8000)
```

## Tests and build

```bash
# service
cd visionfit/service && ./.venv/bin/python -m pytest -q

# frontend
cd visionfit/frontend && npm test && npm run build
```

## What is and isn't verified

- **Verified:** exposure and blur checks flip the decision correctly (good → proceed; blurry or
  dark → recapture), and decisions are recorded with image fingerprint, metrics, provisional
  thresholds and timestamps.
- **Not verified yet:** posture, framing, waist-cord placement, measurement suitability, and any
  actual measurement value. These are later milestones.

## AWS API deployment

The OpenCV service can run on AWS while the frontend remains separately hosted. See
[`deploy/AWS_DEPLOYMENT.md`](deploy/AWS_DEPLOYMENT.md) for the ECS Express Mode container setup,
frontend API URL configuration, cost notes and first-test checklist.

## Hackathon demonstration

Use [docs/HACKATHON_DEMO.md](docs/HACKATHON_DEMO.md) for the three-minute judging flow, capture setup and deployment checklist.
