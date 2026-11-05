# Neon database setup

1. Create a Neon project and copy both pooled and direct Postgres connection strings.
2. Store them server-side as `DATABASE_URL` (pooled application traffic) and
   `DATABASE_URL_UNPOOLED` (direct migrations); never expose either in a `VITE_*` variable.
3. Run migrations in numeric order in the Neon SQL Editor, or run:

   ```bash
   psql "$DATABASE_URL_UNPOOLED" -v ON_ERROR_STOP=1 -f migrations/001_neon_setup.sql
   psql "$DATABASE_URL_UNPOOLED" -v ON_ERROR_STOP=1 -f migrations/002_managed_auth_cleanup.sql
   psql "$DATABASE_URL_UNPOOLED" -v ON_ERROR_STOP=1 -f migrations/003_measurement_path_versions.sql
   psql "$DATABASE_URL_UNPOOLED" -v ON_ERROR_STOP=1 -f migrations/004_tailoring_keypoint_paths.sql
   psql "$DATABASE_URL_UNPOOLED" -v ON_ERROR_STOP=1 -f migrations/005_archive_underbust_circumference.sql
   psql "$DATABASE_URL_UNPOOLED" -v ON_ERROR_STOP=1 -f migrations/006_runtime_integrity.sql
   psql "$DATABASE_URL_UNPOOLED" -v ON_ERROR_STOP=1 -f migrations/007_training_consent.sql
   psql "$DATABASE_URL_UNPOOLED" -v ON_ERROR_STOP=1 -f migrations/008_external_vision_consent.sql
   psql "$DATABASE_URL_UNPOOLED" -v ON_ERROR_STOP=1 -f migrations/009_retryable_capture_deletion.sql
   psql "$DATABASE_URL_UNPOOLED" -v ON_ERROR_STOP=1 -f migrations/010_manual_only_unvalidated_tailoring_paths.sql
   ```

The schema stores structured data and private object-storage references. Body images and videos
should remain in private object storage rather than being stored as Postgres binary data.

VisionFit uses Neon Auth. The browser receives only the Neon Auth URL; the backend verifies bearer
tokens through `NEON_AUTH_JWKS_URL`, resolves `app_users`, and enforces the `admin` role. Configure
`VISIONFIT_BOOTSTRAP_ADMIN_EMAILS` before the first admin signs in. The Neon owner connection string
must never reach the browser.

Migration 010 archives published Roboflow tailoring-point paths and makes those definitions
manual-only until the labeled points have been validated against tape measurements. Historical
measurement values remain attached to their archived path versions for review.

Capture sessions and their linked measurement tables are removed after 30 days without activity
by default (`VISIONFIT_RETENTION_DAYS`). Users can also delete a capture session immediately from
the capture review screen. Each deletion first marks the session as deleting, removes its private object-storage files,
and then deletes the database rows. A storage failure leaves the object keys available for retry.
