# VisionFit measurement-definition registry

A versioned, typed registry of VisionFit body-measurement definitions, built from the four
domain sources in `references/` and Eunice's corrections (which take precedence).

## Sources

- `references/Ginani_Measurement_Guide.pdf` — "Ginani Measurement Guide" (women's).
- `references/fit-measurement-guide-ginani.odt` — "Fit Control, Ease & Measurement System" (ease
  policy: measurements = the body as it is; ease is separate).
- `references/measurement-iinstructions-corrected-2026.pdf` — "Measurement Taking Guide"
  (corrected 2026).
- `references/mens-wear-measurement-instructions.pdf` — "Measurement Taking for Men's Wear".

> Note: these four files sit directly in `references/`, not in a `measurement-guides/`
> subdirectory.

## Version

`MEASUREMENT_REGISTRY_VERSION = "2.2.0"` (semver). Definitions depending on unvalidated
tailoring points are retained for manual tape entry only. Still photos are reference evidence;
automatic candidates come from the slow-turn OpenCV/MediaPipe video estimator.

The core registry contains 13 measurements, including the front/back hip circumference loop.
Underbust remains a manual core row until its own complete loop is annotated. Published
tailoring-point paths are archived until the point labels are validated against tape measurements.

## Schema

Each `MeasurementDefinition` records:

- stable `key` + `displayName`
- anatomical `startPoint` / `endPoint` (or circumference level)
- `path`: `circumference` | `straight` | `surface`
- `captureViews` + `visibility`
- `tapeInstructions`
- `sources` (document + page + verbatim quote)
- `ownerCorrections` (Eunice's overrides)
- `mapping` (CoStudio key + code, Pattern CAD names + body field)
- `ambiguities` (open questions requiring domain review)

Every record is a **body measurement** — exact, with no ease or allowance (see
`BODY_MEASUREMENT_POLICY`; ease belongs in Pattern CAD). The registry also declares
`IMAGE_PLANE_WARNING`: image-plane distances are not body-surface lengths or circumferences.

## Eunice's confirmed definitions (2026-10-12)

Owner-confirmed definitions, taking precedence over conflicting source wording:

1. **Bust point length**: from the **side neck point** to the **fullest point of the bust**
   (surface path, not a vertical drop). Use "fullest point of the bust" in user-facing text, not
   "nipple".
2. **Bust radius**: from the **fullest point of the bust** downward to directly underneath the
   bust, where it meets the chest wall (toward the underbust).
3. **Front shoulder**: straight across the front between the two shoulder points, tape resting
   against the body.
4. **Back shoulder**: between the two shoulder points across the back, following the shoulder
   curvature.
5. **Nape-to-waist**: straight down the centre back to the cord marking the natural waist.
6. **Across chest / across back**: across the respective front/back surface at approximately
   4 inches (101.6 mm) below the shoulder point.

Terminology: **"bust point" = "fullest point of the bust" = "bust apex"** (synonymous).

Retained earlier corrections:

- **Full front length**: starts at the side neck point and follows the body contour over the
  bust/chest to the natural-waist cord.
- **Side waist to knee** (future scope): runs down the side from the natural waist to knee level.

## Integration findings

- **CoStudio**: all 13 records map to an existing `COSTUDIO_MEASUREMENT_FIELDS` key.
- **Pattern CAD**: the user uploads a `.mtb`/`.mmt` measurement table; rows are stored by name
  (matched via `normalizeMeasurementName`, canonical unit mm) — nothing is hardcoded. The 3D
  avatar morph is driven by body landmarks: `height`, `bust`, `waist`, `hip`, `shoulder`,
  `acrossChest`, `underBust`, `lowerAbdomen`, `napeToWaist`, `sideWaistToKnee`, `knee`. VisionFit
  measurements map onto these landmarks where they exist; the remaining measurements
  (`bust_point`, `bust_span`, `bust_radius`, `across_back`, `full_front_length`, and a distinct
  `back_shoulder`) are stored as named rows and available to the user, but do not currently drive
  a morph landmark.

## Tests

`units.test.ts` covers mm/cm/in handling; `registry.test.ts` covers integrity, the corrected
definitions, and the CoStudio / Pattern CAD mappings.
