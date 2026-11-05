# VisionFit — deployment checklist

Consolidated production settings. These live in the AWS console, **not** in committed
files: the server `.env` is gitignored. The deploy script supports creating a new service or
updating the existing service when `ECS_SERVICE_ARN` is set.

## Canonical URLs

| Role | URL |
| --- | --- |
| Frontend (Amplify) | `https://visionfit.ginani.net` |
| Backend API (ECS Express) | `https://gi-4bffebb94e7c42ebaa6094d36fde44ad.ecs.us-east-1.on.aws` |

## Settings to apply

### 1. Amplify — App settings → Environment variables

| Variable | Value |
| --- | --- |
| `VITE_VISIONFIT_API_URL` | `https://gi-4bffebb94e7c42ebaa6094d36fde44ad.ecs.us-east-1.on.aws` (no trailing slash) |
| `VITE_NEON_AUTH_URL` | the Neon Auth endpoint (same value as `NEON_AUTH_BASE_URL` in the server `.env`) |

Save, then **redeploy** so the values are baked into the next build.
The consent-aware frontend was published to the production Amplify `main` branch on 26 October
2026 and verified at the custom domain.

### 2. ECS — service → update → Environment variables

Before deploying the new API image, run unapplied Neon migrations through 010 in numeric order
using the direct connection, as documented in `service/migrations/README.md`. Migration 010
archives unvalidated tailoring-point paths and makes those measurement definitions manual-only.

| Variable | Value |
| --- | --- |
| `VISIONFIT_CORS_ORIGINS` | `https://visionfit.ginani.net,http://localhost:5173` |
| `VISIONFIT_RETENTION_DAYS` | `30` |

Roboflow is not used by the current capture workflow. Keep `ROBOFLOW_ENABLED` unset or `false`;
the API's still-image tailoring-point estimator is retired, and the video estimator does not use
those unvalidated points. For this existing service, set `ECS_SERVICE_ARN` to its ARN and run
`aws-ecs-express.sh` to update the existing ECS Express service. This mode does not create a second
service.

## Verification

1. `curl https://gi-4bffebb94e7c42ebaa6094d36fde44ad.ecs.us-east-1.on.aws/api/health`
   → `{"status":"ok","opencv":"5.0.0",...}`
2. Open `https://visionfit.ginani.net`, sign in, and submit one consented slow-turn video. Confirm
   optional still photos are described as reviewer evidence only.
3. Browser devtools → Network: requests hit the `gi-4bffebb...on.aws` host with no CORS errors.
4. `/api/health` reports `measurementVision.measurementPathEnabled: false`.
5. In a test account, confirm still-photo capture is reference-only and no capture request is sent
   to Roboflow. Confirm complete slow turns return only review-required estimates.

## References

- `AMPLIFY_HOSTING.md` — Amplify build, custom domain, SPA routing
- `AWS_DEPLOYMENT.md` — ECS Express Mode API deployment and first-test runbook
