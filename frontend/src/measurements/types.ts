export type LengthUnit = 'mm' | 'cm' | 'in'

export type MeasurementScope = 'core' | 'future'

/**
 * How the tape (or the vision estimate) travels between the landmarks.
 * `straight` = linear point-to-point distance; `surface` = follows the body
 * contour; `circumference` = around the body at a level.
 */
export type MeasurementPath = 'circumference' | 'straight' | 'surface'

export type CaptureView = 'front' | 'side' | 'back'

export interface SourceReference {
  /** Stable short document name, e.g. "Ginani_Measurement_Guide.pdf". */
  document: string
  page?: string
  /** Verbatim wording from the source (trimmed). */
  quote?: string
}

export interface IntegrationMapping {
  /** CoStudio `COSTUDIO_MEASUREMENT_FIELDS` key (references/costudio/assets/measurement-schema.js). */
  costudioKey: string | null
  /** CoStudio `code` field when present (e.g. "w-bust-circ"). */
  costudioCode: string | null
  /**
   * Pattern CAD measurement name(s) — the row name(s) in the user's `.mtb`/`.mmt`
   * measurement table (matched case-insensitively via `normalizeMeasurementName`).
   * Pattern CAD stores measurements by name, not position — nothing is hardcoded.
   */
  patternCadNames: string[]
  /**
   * Pattern CAD 3D body landmark this measurement drives, or null when it is
   * stored as a named measurement but does not currently drive the avatar morph.
   */
  patternCadLandmark: string | null
  notes?: string
}

export interface MeasurementDefinition {
  /** Stable machine key (matches CoStudio key where one exists). */
  key: string
  displayName: string
  scope: MeasurementScope
  category: string
  /** Anatomical start point or circumference level. */
  startPoint: string
  /** Anatomical end point; empty string for circumferences. */
  endPoint: string
  path: MeasurementPath
  pathNote?: string
  /** Views the vision pipeline needs to attempt this measurement. */
  captureViews: CaptureView[]
  /** What must be visible / landmarked for vision to attempt this measurement. */
  visibility: string
  /** Targeted tape-measurement instructions a human can follow directly. */
  tapeInstructions: string
  sources: SourceReference[]
  /** Eunice's corrections that take precedence over the sources. */
  ownerCorrections: string[]
  mapping: IntegrationMapping
  /** Open questions that need domain review before any inference. */
  ambiguities: string[]
}

export const BODY_MEASUREMENT_POLICY =
  'Exact body measurement — no garment ease or seam allowance. Ease is controlled in Pattern CAD.'
