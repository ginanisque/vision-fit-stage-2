import type { MeasurementDefinition } from './types'

/**
 * Versioned measurement-definition registry for VisionFit.
 *
 * Version: see MEASUREMENT_REGISTRY_VERSION.
 *
 * Every record is a BODY measurement — exact, with no garment ease or allowance
 * (ease belongs in Pattern CAD). Vision must not assume image-plane distances
 * equal body-surface lengths or circumferences; each record declares its path
 * explicitly and any open question is listed under `ambiguities`.
 */

export const MEASUREMENT_REGISTRY_VERSION = '2.2.0'

export const IMAGE_PLANE_WARNING =
  'Image-plane distances are NOT body-surface lengths or circumferences. ' +
  'Each record declares its measurement path; vision must not equate pixels to the value.'

export const bust: MeasurementDefinition = {
  key: 'bust',
  displayName: 'Bust',
  scope: 'core',
  category: 'Circumference',
  startPoint: 'Fullest part of the bust',
  endPoint: '',
  path: 'circumference',
  pathNote: 'Tape level front and back.',
  captureViews: ['front', 'back'],
  visibility: 'The six annotated bust-loop keypoints are visible across front and back views.',
  tapeInstructions:
    'Measure around the fullest part of the bust, keeping the tape level front and back. ' +
    'Stand at the side of the person to ensure the tape does not slip down at the back.',
  sources: [
    {
      document: 'Ginani_Measurement_Guide.pdf',
      page: 'p.1',
      quote: 'Bust: Measure around the fullest part of the bust. Keep the tape level front and back.',
    },
    {
      document: 'measurement-iinstructions-corrected-2026.pdf',
      page: 'p.1',
      quote: 'Measure over the fullest part of bust, keeping the tape level at the back.',
    },
  ],
  ownerCorrections: [],
  mapping: {
    costudioKey: 'bust',
    costudioCode: 'w-bust-circ',
    patternCadNames: ['bust', 'full bust'],
    patternCadLandmark: 'bust',
  },
  ambiguities: [],
}

export const underbust: MeasurementDefinition = {
  key: 'underbust',
  displayName: 'Underbust',
  scope: 'core',
  category: 'Circumference',
  startPoint: 'Rib cage directly under the bust',
  endPoint: '',
  path: 'circumference',
  captureViews: ['front', 'side'],
  visibility: 'The current underbust_left/right annotations are bust-radius endpoints, not a circumference loop. Underbust circumference remains manual until a future loop is defined.',
  tapeInstructions: 'Measure around the rib cage directly under the bust.',
  sources: [
    {
      document: 'Ginani_Measurement_Guide.pdf',
      page: 'p.1',
      quote: 'Underbust: Measure around the rib cage directly under the bust.',
    },
  ],
  ownerCorrections: [],
  mapping: {
    costudioKey: 'under_bust',
    costudioCode: 'w-under-bust',
    patternCadNames: ['under bust', 'underbust'],
    patternCadLandmark: 'underBust',
  },
  ambiguities: [],
}

export const bustPoint: MeasurementDefinition = {
  key: 'bust_point',
  displayName: 'Bust point length',
  scope: 'core',
  category: 'Bust control',
  startPoint: 'Side neck point',
  endPoint: 'Fullest point of the bust',
  path: 'surface',
  pathNote: 'Follows the body contour; not a vertical drop.',
  captureViews: ['front', 'side'],
  visibility: 'Side neck point and the fullest point of the bust visible from the front.',
  tapeInstructions:
    'Measure with the tape from the side neck point to the fullest point of the bust.',
  sources: [
    {
      document: 'Ginani_Measurement_Guide.pdf',
      page: 'p.1',
      quote: 'Bust Point Length: Measure from the front neck point vertically to the bust point.',
    },
    {
      document: 'measurement-iinstructions-corrected-2026.pdf',
      page: 'p.2',
      quote: 'Bust Point: Measure from the front neck point to the nipple.',
    },
  ],
  ownerCorrections: [
    'Eunice (2026-10-12): measure from the SIDE NECK POINT to the fullest point of the bust; not a vertical drop. Use "fullest point of the bust" in user-facing text, not "nipple".',
  ],
  mapping: {
    costudioKey: 'bust_point',
    costudioCode: 'w-bust-point',
    patternCadNames: ['bust point', 'bust point length'],
    patternCadLandmark: null,
    notes: 'CoStudio says "front neck point to the bust point"; superseded by the confirmed side-neck-point → fullest-bust definition. Stored as a named measurement; no dedicated morph landmark.',
  },
  ambiguities: [],
}

export const bustSpan: MeasurementDefinition = {
  key: 'bust_span',
  displayName: 'Bust span',
  scope: 'core',
  category: 'Bust control',
  startPoint: 'Fullest point of the bust (one side)',
  endPoint: 'Fullest point of the bust (other side)',
  path: 'straight',
  pathNote: 'Horizontal distance between the two fullest points of the bust (bust apex).',
  captureViews: ['front'],
  visibility: 'Both fullest points of the bust visible from the front.',
  tapeInstructions: 'Measure horizontally from one fullest point of the bust to the other.',
  sources: [
    {
      document: 'Ginani_Measurement_Guide.pdf',
      page: 'p.1',
      quote: 'Bust Span: Measure from bust point to bust point horizontally.',
    },
    {
      document: 'measurement-iinstructions-corrected-2026.pdf',
      page: 'p.2',
      quote: 'Bust Span: This is the distance between the nipples.',
    },
  ],
  ownerCorrections: [
    'Eunice (2026-10-12): "bust point" = "fullest point of the bust" = "bust apex" — the terms are synonymous.',
  ],
  mapping: {
    costudioKey: 'bust_span',
    costudioCode: 'w-bust-span',
    patternCadNames: ['bust span'],
    patternCadLandmark: null,
    notes: 'Stored as a named measurement; no dedicated morph landmark.',
  },
  ambiguities: [],
}

export const bustRadius: MeasurementDefinition = {
  key: 'bust_radius',
  displayName: 'Bust radius',
  scope: 'core',
  category: 'Bust control',
  startPoint: 'Fullest point of the bust',
  endPoint: 'Directly underneath the bust, where the bust meets the chest wall',
  path: 'straight',
  pathNote: 'Straight line downward toward the underbust.',
  captureViews: ['front', 'side'],
  visibility: 'Fullest point of the bust and the underbust line visible.',
  tapeInstructions:
    'Measure from the fullest point of the bust to directly underneath the bust, where the ' +
    'bust meets the chest wall (downward toward the underbust).',
  sources: [
    {
      document: 'Ginani_Measurement_Guide.pdf',
      page: 'p.1-2',
      quote:
        'Bust Radius: Measure from the bust point to where the bust curve meets the chest wall. Take this measurement straight, not around the body.',
    },
  ],
  ownerCorrections: [
    'Eunice (2026-10-12): measure downward from the fullest point of the bust to directly underneath the bust, where it meets the chest wall (toward the underbust).',
  ],
  mapping: {
    costudioKey: 'bust_radius',
    costudioCode: 'w-bust-radius',
    patternCadNames: ['bust radius'],
    patternCadLandmark: null,
    notes: 'Stored as a named measurement; no dedicated morph landmark.',
  },
  ambiguities: [],
}

export const waist: MeasurementDefinition = {
  key: 'waist',
  displayName: 'Waist',
  scope: 'core',
  category: 'Circumference',
  startPoint: 'Natural waistline (hollow of the back, below the rib cage, above the hip bone)',
  endPoint: '',
  path: 'circumference',
  captureViews: ['front', 'back'],
  visibility: 'Natural waistline visible; the high-contrast waist cord marks this level across views.',
  tapeInstructions: 'Measure around the natural waistline identified at the small of the back.',
  sources: [
    {
      document: 'Ginani_Measurement_Guide.pdf',
      page: 'p.1',
      quote: 'Waist: Measure around the natural waistline previously identified.',
    },
    {
      document: 'measurement-iinstructions-corrected-2026.pdf',
      page: 'p.4',
      quote: 'Waist: Take measurement around natural waistline of the figure.',
    },
  ],
  ownerCorrections: [],
  mapping: {
    costudioKey: 'waist',
    costudioCode: 'w-waistline',
    patternCadNames: ['waist', 'natural waist'],
    patternCadLandmark: 'waist',
  },
  ambiguities: [],
}

export const hip: MeasurementDefinition = {
  key: 'hip',
  displayName: 'Hip',
  scope: 'core',
  category: 'Circumference',
  startPoint: 'Fullest hip/seat level',
  endPoint: '',
  path: 'circumference',
  pathNote: 'Level loop through the annotated side, centre-front and centre-back hip points.',
  captureViews: ['front', 'back'],
  visibility: 'hip_side_left/right, hip_center_front and hip_center_back visible in their assigned views.',
  tapeInstructions: 'Measure level around the fullest part of the hips and seat without compressing the body.',
  sources: [{ document: 'Garment Fitting Body Landmarks COCO v6', quote: 'hip_center_front, hip_center_back, hip_side_right, hip_side_left' }],
  ownerCorrections: [],
  mapping: {
    costudioKey: 'hip',
    costudioCode: 'w-hip-circ',
    patternCadNames: ['hip', 'full hip', 'seat'],
    patternCadLandmark: 'hip',
  },
  ambiguities: [],
}

export const frontShoulder: MeasurementDefinition = {
  key: 'front_shoulder',
  displayName: 'Front shoulder',
  scope: 'core',
  category: 'Upper body width',
  startPoint: 'Shoulder point (one side)',
  endPoint: 'Shoulder point (other side)',
  path: 'straight',
  pathNote: 'Straight across the front, tape resting against the body.',
  captureViews: ['front'],
  visibility: 'Both shoulder points visible from the front.',
  tapeInstructions:
    'Measure straight across the front between the two shoulder points, with the tape resting against the body.',
  sources: [
    {
      document: 'measurement-iinstructions-corrected-2026.pdf',
      page: 'p.3',
      quote: 'Front Shoulder: Take this measurement from shoulder point to shoulder point with the individual facing you.',
    },
    {
      document: 'mens-wear-measurement-instructions.pdf',
      page: 'p.1',
      quote: 'Front Shoulder: From the front, measure the shoulder. Measure from shoulder point to shoulder point.',
    },
  ],
  ownerCorrections: [
    'Eunice (2026-10-12): measure straight across the front between the two shoulder points, tape resting against the body.',
  ],
  mapping: {
    costudioKey: 'front_shoulder',
    costudioCode: 'w-front-shoulder-measure',
    patternCadNames: ['front shoulder', 'shoulder width', 'across shoulder'],
    patternCadLandmark: 'shoulder',
    notes: 'CoStudio label is "Front shoulder width". Pattern CAD maps this to the single shared "shoulder" landmark.',
  },
  ambiguities: [],
}

export const backShoulder: MeasurementDefinition = {
  key: 'back_shoulder',
  displayName: 'Back shoulder',
  scope: 'core',
  category: 'Upper body width',
  startPoint: 'Shoulder point (one side)',
  endPoint: 'Shoulder point (other side)',
  path: 'surface',
  pathNote: 'Across the back, following the shoulder curvature.',
  captureViews: ['back'],
  visibility: 'Both shoulder points visible from the back.',
  tapeInstructions:
    'Measure between the two shoulder points across the back, following the shoulder curvature.',
  sources: [
    {
      document: 'measurement-iinstructions-corrected-2026.pdf',
      page: 'p.3',
      quote: 'Back Shoulder: Take this measurement from shoulder point to shoulder point with the individual backing you.',
    },
    {
      document: 'mens-wear-measurement-instructions.pdf',
      page: 'p.1',
      quote: 'Back Shoulder: From the back, measure the shoulder. Measure from shoulder point to shoulder point.',
    },
  ],
  ownerCorrections: [
    'Eunice (2026-10-12): measure between the two shoulder points across the back, following the shoulder curvature.',
  ],
  mapping: {
    costudioKey: 'back_shoulder',
    costudioCode: 'w-back-shoulder-measure',
    patternCadNames: ['back shoulder'],
    patternCadLandmark: 'shoulder',
    notes:
      'CoStudio label is "Back shoulder width". Pattern CAD maps shoulder to a single shared landmark (aliases: front shoulder / shoulder width / across shoulder); "back shoulder" is stored as a named measurement without its own morph landmark.',
  },
  ambiguities: [
    'Pattern CAD collapses front and back shoulder into one "shoulder" value; the back-shoulder value has no direct CAD field.',
  ],
}

export const acrossChest: MeasurementDefinition = {
  key: 'across_chest',
  displayName: 'Across chest',
  scope: 'core',
  category: 'Upper body width',
  startPoint: 'One side of the front, 4 in (101.6 mm) below the shoulder point',
  endPoint: 'Other side of the front, 4 in (101.6 mm) below the shoulder point',
  path: 'surface',
  pathNote: 'Across the front surface at approximately 4 inches (101.6 mm) below the shoulder point.',
  captureViews: ['front'],
  visibility: 'Front surface at 4 in (101.6 mm) below the shoulder points visible.',
  tapeInstructions:
    'Measure across the front surface at approximately 4 inches (101.6 mm) below the shoulder point.',
  sources: [
    {
      document: 'Ginani_Measurement_Guide.pdf',
      page: 'p.2',
      quote: 'Across Chest: Measure across the front approximately 4 inches below the shoulder point.',
    },
    {
      document: 'measurement-iinstructions-corrected-2026.pdf',
      page: 'p.2',
      quote: 'Across Chest: Measure approximately 4 inches below the shoulder point.',
    },
    {
      document: 'mens-wear-measurement-instructions.pdf',
      page: 'p.1',
      quote: 'Across Chest: Measure the chest from the crease of the arm to the other arm crease.',
    },
  ],
  ownerCorrections: [
    'Eunice (2026-10-12): measure across the front surface at approximately 4 inches (101.6 mm) below the shoulder point.',
  ],
  mapping: {
    costudioKey: 'across_chest',
    costudioCode: 'w-across-chest (2)',
    patternCadNames: ['across chest', 'chest width'],
    patternCadLandmark: 'acrossChest',
  },
  ambiguities: [],
}

export const acrossBack: MeasurementDefinition = {
  key: 'across_back',
  displayName: 'Across back',
  scope: 'core',
  category: 'Upper body width',
  startPoint: 'One side of the back, 4 in (101.6 mm) below the shoulder point',
  endPoint: 'Other side of the back, 4 in (101.6 mm) below the shoulder point',
  path: 'surface',
  pathNote: 'Across the back surface at approximately 4 inches (101.6 mm) below the shoulder point.',
  captureViews: ['back'],
  visibility: 'Back surface at 4 in (101.6 mm) below the shoulder points visible.',
  tapeInstructions:
    'Measure across the back surface at approximately 4 inches (101.6 mm) below the shoulder point.',
  sources: [
    {
      document: 'Ginani_Measurement_Guide.pdf',
      page: 'p.2',
      quote: 'Across Back: Measure across the back halfway between the shoulder line and back bust line.',
    },
    {
      document: 'measurement-iinstructions-corrected-2026.pdf',
      page: 'p.3',
      quote: 'Across Back: Measure the width of the back halfway between the shoulder and back bust line.',
    },
    {
      document: 'mens-wear-measurement-instructions.pdf',
      page: 'p.1',
      quote: 'Across Back: Measure the back from the crease of the arm to the other arm crease.',
    },
  ],
  ownerCorrections: [
    'Eunice (2026-10-12): measure across the back surface at approximately 4 inches (101.6 mm) below the shoulder point.',
  ],
  mapping: {
    costudioKey: 'across_back',
    costudioCode: 'w-acrossback-meas2',
    patternCadNames: ['across back'],
    patternCadLandmark: null,
    notes: 'Stored as a named measurement; no dedicated morph landmark.',
  },
  ambiguities: [],
}

export const napeToWaist: MeasurementDefinition = {
  key: 'nape_to_waist',
  displayName: 'Nape to waist',
  scope: 'core',
  category: 'Vertical length',
  startPoint: 'Nape (base of the neck at centre back)',
  endPoint: 'Cord marking the natural waist (centre back)',
  path: 'straight',
  pathNote: 'Straight down the centre back.',
  captureViews: ['back'],
  visibility: 'Nape and the waist cord (centre back) visible from the back.',
  tapeInstructions: 'Measure from the nape straight down the centre back to the cord marking the natural waist.',
  sources: [
    {
      document: 'Ginani_Measurement_Guide.pdf',
      page: 'p.2',
      quote: 'Nape to Waist: Measure from the nape straight down to the waistline.',
    },
    {
      document: 'measurement-iinstructions-corrected-2026.pdf',
      page: 'p.4',
      quote: 'Nape to waist Length: Measure from the nape (the base) of the neck, to the waistline.',
    },
  ],
  ownerCorrections: [
    'Eunice (2026-10-12): measure from the nape straight down the centre back to the cord marking the natural waist.',
  ],
  mapping: {
    costudioKey: 'nape_to_waist',
    costudioCode: 'w-nape-waist',
    patternCadNames: ['nape to waist', 'back length'],
    patternCadLandmark: 'napeToWaist',
  },
  ambiguities: [],
}

export const fullFrontLength: MeasurementDefinition = {
  key: 'full_front_length',
  displayName: 'Full front length',
  scope: 'core',
  category: 'Vertical length',
  startPoint: 'Side neck point',
  endPoint: 'Cord on the waist (front)',
  path: 'surface',
  pathNote: 'Follows the body contour over the chest (women: over the fullest part of the bust) to the cord on the waist.',
  captureViews: ['front', 'side'],
  visibility: 'Side neck point, chest/bust contour and the waist cord (front) visible.',
  tapeInstructions:
    'Measure from the side neck point, following the body contour over the chest (for women, ' +
    'over the fullest part of the bust), to the cord on the waist at the front.',
  sources: [
    {
      document: 'Ginani_Measurement_Guide.pdf',
      page: 'p.2',
      quote: 'Full Front Length: Measure from the front neck point, over the fullest part of the bust, to the waistline.',
    },
    {
      document: 'measurement-iinstructions-corrected-2026.pdf',
      page: 'p.4',
      quote: 'Full Front Length: Measure from the front neck point, over the fullest part of the bust, to the waistline.',
    },
    {
      document: 'mens-wear-measurement-instructions.pdf',
      page: 'p.1',
      quote: 'Full Front Length: Measure from the side neck point over the chest to the waist line.',
    },
  ],
  ownerCorrections: [
    'Eunice (2026-10-12): start at the SIDE NECK POINT (not the "front neck point" as written in the women\'s guides).',
    'Eunice (2026-10-12): men\'s full front length is measured from the side neck point over the chest to the CORD on the waist.',
  ],
  mapping: {
    costudioKey: 'full_front_length',
    costudioCode: 'w-full-front-length',
    patternCadNames: ['full front length'],
    patternCadLandmark: null,
    notes: 'Stored as a named measurement; no dedicated morph landmark.',
  },
  ambiguities: [],
}

export const sideWaistToKnee: MeasurementDefinition = {
  key: 'side_waist_to_knee',
  displayName: 'Side waist to knee',
  scope: 'future',
  category: 'Lower body length',
  startPoint: 'Natural waist at the side (side waist point)',
  endPoint: 'Knee level',
  path: 'surface',
  pathNote: 'Down the side of the body.',
  captureViews: ['side'],
  visibility: 'Side waist point and knee level visible from the side.',
  tapeInstructions: 'Measure from the natural waist at the side, down the side to knee level.',
  sources: [
    {
      document: 'measurement-iinstructions-corrected-2026.pdf',
      page: 'p.6',
      quote: 'Side waist to knee: Take this measurement down the center front form the waistline down to the knee.',
    },
    {
      document: 'measurement-iinstructions-corrected-2026.pdf',
      page: 'p.6',
      quote: 'Side waist to knee: Take measurement from side waist point down to the knee.',
    },
    {
      document: 'mens-wear-measurement-instructions.pdf',
      page: 'p.1',
      quote: 'Side Waist to Knee: Measure from the waist line down to the knee.',
    },
  ],
  ownerCorrections: [
    'Eunice (2026-10-12): measure from the natural waist at the SIDE, down the side to knee level. The centre-front wording in the source is incorrect.',
  ],
  mapping: {
    costudioKey: 'side_waist_to_knee',
    costudioCode: 'w-side-waist-to-knee',
    patternCadNames: ['side waist to knee', 'waist to knee'],
    patternCadLandmark: 'sideWaistToKnee',
  },
  ambiguities: [
    'The source contains two conflicting lines (centre-front vs side waist); Eunice resolves to the side. "Knee level" exact landmark (top/mid knee) is not specified.',
  ],
}

export const MEASUREMENT_REGISTRY: readonly MeasurementDefinition[] = [
  bust,
  underbust,
  bustPoint,
  bustSpan,
  bustRadius,
  waist,
  hip,
  frontShoulder,
  backShoulder,
  acrossChest,
  acrossBack,
  napeToWaist,
  fullFrontLength,
  sideWaistToKnee,
]

export const CORE_MEASUREMENTS: readonly MeasurementDefinition[] = MEASUREMENT_REGISTRY.filter(
  (m) => m.scope === 'core',
)

export const FUTURE_MEASUREMENTS: readonly MeasurementDefinition[] = MEASUREMENT_REGISTRY.filter(
  (m) => m.scope === 'future',
)

const registryByKey = new Map(MEASUREMENT_REGISTRY.map((m) => [m.key, m]))

export function getMeasurement(key: string): MeasurementDefinition | undefined {
  return registryByKey.get(key)
}

export function coreMeasurementKeys(): string[] {
  return CORE_MEASUREMENTS.map((m) => m.key)
}


