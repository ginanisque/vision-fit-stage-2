# VisionFit quality service (VF-0)

A local Python/FastAPI service with **verified, pinned OpenCV 5** that performs a
real exposure + blur quality check and returns a **recorded decision**
(`recapture` or `proceed`).

## Requirements

- Python 3.12 (the system here lacks `python3-venv`; see setup below).
- OpenCV 5.0.0.93 (pinned in `requirements.txt`). Do **not** substitute OpenCV 4.

## Setup

The workspace image does not have `python3-venv` (no `ensurepip`), so the venv is
created without pip and pip is bootstrapped from the official installer:

```bash
cd visionfit/service
python3 -m venv --without-pip .venv
curl -sSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
./.venv/bin/python /tmp/get-pip.py --quiet
./.venv/bin/python -m pip install -r requirements.txt
```

Verify OpenCV 5:

```bash
./.venv/bin/python -c "import cv2; print(cv2.__version__)"   # 5.0.0
```

## Optional: MediaPipe Pose (posture + turn coverage)

Posture, view orientation and full-turn coverage use MediaPipe Pose landmarks. It is
optional — without it those checks honestly return `unknown` and request human review.

Install **without its OpenCV dependency** so the pinned headless OpenCV 5 stays intact:

```bash
./.venv/bin/python -m pip install --no-deps mediapipe
./.venv/bin/python -m pip install absl-py flatbuffers sounddevice matplotlib
# download the pose model (not bundled)
mkdir -p models
curl -sL -o models/pose_landmarker_full.task \
  'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task'
```

`pip install mediapipe` (with deps) pulls `opencv-contrib-python`, which needs GUI
libraries and would break the headless OpenCV 5 pin — hence the `--no-deps` step.

## Run

```bash
cd visionfit/service
./.venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

Endpoints:

- `GET  /api/health` — service + OpenCV version.
- `POST /api/quality` — authenticated multipart form: `view` (`front`|`side`) + `consent` + `file`
  (image). Returns a decision record (VF-0, exposure + blur only; 20 MiB limit).
- `POST /api/capture` — authenticated multipart form: `view` + `consent` + `file`. Consent-gated
  exposure/blur, contrast-silhouette framing, cord candidate and pose-landmark
  posture evidence (VF-2). An optional `training_consent` records whether images in the session
  may be included in the admin training export. Without opt-in, admin capture review does not
  return media download links. Still images are reference evidence only; this endpoint does not run
  Roboflow tailoring-point inference or generate measurements.
- `POST /api/turn-video` — authenticated multipart form: `consent`, optional `height_mm`,
  optional `training_consent`, and `file` (video). Duration, sampled exposure/blur and
  pose-orientation turn coverage are checked. Complete, quality-passing turns produce experimental
  MediaPipe/OpenCV estimates from selected front/side/back frames, saved review-only to the linked
  measurement table. Existing torso circumferences are supplemented by experimental neck, upper
  arm, thigh and calf circumference candidates, arm length, side waist-to-knee length, and the
  left-to-right shoulder width. Every candidate requires human tape confirmation.
- `POST /api/measurement-estimates` — returns `410 Gone`. Still-image estimates based on
  unvalidated tailoring points are disabled; use the slow-turn video endpoint for experimental
  candidates. Manual measurement entry remains available.
- `GET  /api/decisions` — Neon-backed capture analyses (admin only).
- `GET  /api/measurements/definitions` — versioned backend measurement registry.
- `POST /api/measurement-tables` — create a pending measurement table for a subject.
- `GET  /api/measurement-tables/{id}` — retrieve a table in `mm`, `cm` or `in`.
- `PUT  /api/measurement-tables/{id}/measurements/{key}` — record an estimated or reviewed value.
- `GET  /api/admin/training-export` — download a ZIP containing images only from capture sessions
  with recorded training consent. The archive includes a de-identified manifest with export-local pseudonymous
  subject/sequence IDs and consent provenance; it excludes account identifiers and measurements.
  The images are unannotated and must be reviewed/labeled before model training. Split by
  `subject_id` to keep each person in only one dataset split. Admin capture-review media links are
  also withheld for sessions without training consent.
- `GET  /api/admin/measurement-paths` — list published and draft ordered keypoint paths.
- `PUT  /api/admin/measurement-paths/{key}/draft` — create or update an admin path draft.
- `POST /api/admin/measurement-paths/{key}/publish` — currently returns `409` until tailoring
  point labels are validated against tape measurements. Historical published versions remain
  archived for review.
- `DELETE /api/capture-sessions/{id}` — remove the authenticated caller's photos, analysis data and
  linked measurement table.

## Test

```bash
cd visionfit/service
./.venv/bin/python -m pytest -q
```

## Notes

- Quality thresholds are **provisional** and not domain-approved.
- Framing/cord/posture are provisional candidates, not measurement/export approval;
  natural-waist placement, camera level/distance and anatomical completeness require
  human review.
- Posture and turn coverage need MediaPipe (see above); without it they return
  `unknown` and request review.
- Capture metadata, analyses, landmarks, and measurement tables are stored in Neon Postgres.
  Capture binaries are private Neon Object Storage objects; Postgres stores object keys and metadata.
- Capture sessions and linked measurement tables are automatically deleted after 30 inactive days
  by default (`VISIONFIT_RETENTION_DAYS=30`), or sooner through the authenticated delete endpoint.
- Values are stored canonically in millimetres; estimated values require confidence and admin review.

## Measurement-estimate status

Still photos are reference evidence only and are not sent to Roboflow or used to calculate
measurements. The legacy still-image measurement endpoint returns `410 Gone`, and the ordered
Roboflow tailoring-point paths are archived/manual-only until validated against tape measurements.
Complete slow-turn videos can produce experimental OpenCV/MediaPipe candidates, including
circumferences and lengths; all candidates are review-only and must be confirmed with a tape.

The video estimator uses pose landmarks, silhouette widths, and height scaling. Its calibration
profile is separate from the archived tailoring-point paths and must be trained from professionally
measured labels before its accuracy can be claimed.

The geometry estimator is intentionally separate from learned correction. Save professionally
measured labels in CSV columns named `raw_<measurement>_mm` and `tape_<measurement>_mm`, with one
row per consenting subject. Fit an auditable baseline profile with:

```bash
PYTHONPATH=. ./.venv/bin/python scripts/train_measurement_calibration.py labels.csv models/vf3-calibration.json
```

Set `VISIONFIT_MEASUREMENT_MODEL_PATH=models/vf3-calibration.json` when running the API. The API
returns the loaded model version and its observed MAE as uncertainty. Synthetic reference images
must not be included as accuracy labels.

Validate every COCO export before training. The validator rejects source-video leakage across
splits, fewer than 50 images, fewer than five manifested subjects, and missing subject provenance.
Start from `../docs/subject_manifest.example.csv`; every exported source group must have exactly one row:

```bash
./.venv/bin/python scripts/validate_coco_dataset.py ../../dataset-training/export.zip \
  --manifest ../../dataset-training/subjects.csv
```

## AWS container

Dockerfile packages the pinned OpenCV 5 service and MediaPipe Pose runtime, then downloads the
official pose task during the container build. For a one-task ECS Express Mode deployment, frontend URL configuration,
health checks and first-test steps, see [`../deploy/AWS_DEPLOYMENT.md`](../deploy/AWS_DEPLOYMENT.md).

## Neon persistence

The Postgres migrations are in [`migrations`](migrations/).
See [`migrations/README.md`](migrations/README.md) for connection and setup instructions.
