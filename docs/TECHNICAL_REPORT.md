# Ginani VisionFit — technical report

**Status:** working prototype; measurement candidates remain experimental and require human tape
validation.

## Problem and users

VisionFit guides a customer through consent, height entry, and one slow-turn video. Optional
front/side/back stills provide reference evidence for human review only. The system aims to give
garment specialists traceable posture and measurement evidence rather than presenting an
unreviewed image-derived number as a tailoring measurement.

## System design

The React, TypeScript and Vite client is hosted as a static app on AWS Amplify. The Python/FastAPI
service runs in an AWS ECS Express Mode container. Neon Auth supplies browser identity; the API
verifies bearer tokens against its JWKS endpoint. Neon Postgres stores consent, capture metadata,
landmarks, versioned measurement paths, and result records. Capture binaries are kept in private
Neon Object Storage. The data flow and review/recapture loop are shown in
[`ARCHITECTURE.md`](./ARCHITECTURE.md).

The container pins `opencv-python-headless==5.0.0.93` (OpenCV 5.0.0). OpenCV handles image decode,
exposure and blur checks, framing evidence, and video sampling. MediaPipe Pose supplies posture and
turn-orientation landmarks. For a complete, quality-passing slow turn, the service selects clear
front, side, and back frames and runs the experimental geometry estimator using entered height for
scale. It emits torso circumference candidates plus neck, upper arm, thigh, calf, shoulder-width,
arm-length, and side-waist-to-knee candidates where their image evidence is sufficient. Candidates
are review-only; existing reviewed values are never overwritten. The new limb estimates are not
validated against professional tape measurements and may be absent when pose or silhouette evidence
is insufficient.

The legacy still-photo estimate route returns `410 Gone`. Optional stills are retained for review
only, and capture endpoints do not send them to Roboflow. The Roboflow integration now rejects
collapsed/insufficient keypoint outputs; ordered paths reject collapsed segments and degenerate
closed loops. Migration 010 archives published tailoring-point paths and makes their definitions
manual-only until the labels have been validated against tape measurements. The administrator path
publisher is also disabled during that period.

## Decisions, review, and safety

The capture workflow converts low-quality evidence into recapture requests and uncertain evidence
into human review. Video estimates always require review. Existing tailoring definitions remain
available for manual tape entry; underbust remains manual. A human tape measurement is still
required; the system has no validated accuracy claim or export approval path.

Customers can delete a capture session and its linked measurement table immediately. By default,
inactive sessions and linked measurement tables are removed after 30 days. The cleanup deletes
private objects before their database references and logs failures so a later run can retry.

## Deployment and operation

Build and local run commands are in [`../README.md`](../README.md). ECS and Amplify configuration,
Secrets Manager keys, update workflow, CORS settings, and live smoke tests are in
[`../deploy/AWS_DEPLOYMENT.md`](../deploy/AWS_DEPLOYMENT.md) and
[`../deploy/DEPLOY_CHECKLIST.md`](../deploy/DEPLOY_CHECKLIST.md). Database migrations are listed in
[`../service/migrations/README.md`](../service/migrations/README.md).

The deployment update script can target an existing ECS Express service using `ECS_SERVICE_ARN`.
Production must receive migration 010 and a new ECS deployment for the manual-only tailoring paths
and disabled still-estimate route to match this code.

## Evaluation and limitations

Automated tests cover API authorization and consent, upload bounds, image-quality failure cases,
Roboflow collapse rejection, degenerate path blocking, video geometry candidates, unit conversions,
and frontend capture behavior. They use synthetic fixtures and do not measure real-person accuracy.
Posture, framing, camera position, cord placement, height calibration and the video estimator remain
provisional. No evaluation against professional tape measurements is available.

The reproducible test commands and evidence limitations are recorded in
[`EVALUATION.md`](./EVALUATION.md). Production endpoint reachability is not evidence of measurement
accuracy or successful tape validation.
