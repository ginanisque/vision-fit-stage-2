import { describe, expect, it } from 'vitest'
import { BODY_MEASUREMENT_POLICY } from './types'
import {
  CORE_MEASUREMENTS,
  FUTURE_MEASUREMENTS,
  MEASUREMENT_REGISTRY,
  MEASUREMENT_REGISTRY_VERSION,
  coreMeasurementKeys,
  getMeasurement,
} from './registry'

const EXPECTED_CORE_KEYS = [
  'bust',
  'underbust',
  'bust_point',
  'bust_span',
  'bust_radius',
  'waist',
  'hip',
  'front_shoulder',
  'back_shoulder',
  'across_chest',
  'across_back',
  'nape_to_waist',
  'full_front_length',
]

describe('registry integrity', () => {
  it('is versioned with a semver string', () => {
    expect(MEASUREMENT_REGISTRY_VERSION).toMatch(/^\d+\.\d+\.\d+$/)
  })

  it('has exactly the 13 core measurements in the required order', () => {
    expect(CORE_MEASUREMENTS).toHaveLength(13)
    expect(coreMeasurementKeys()).toEqual(EXPECTED_CORE_KEYS)
  })

  it('records side waist to knee as future scope without expanding core', () => {
    expect(FUTURE_MEASUREMENTS.map((m) => m.key)).toEqual(['side_waist_to_knee'])
    expect(CORE_MEASUREMENTS.map((m) => m.key)).not.toContain('side_waist_to_knee')
  })

  it('has unique keys across the whole registry', () => {
    const keys = MEASUREMENT_REGISTRY.map((m) => m.key)
    expect(new Set(keys).size).toBe(keys.length)
  })

  it('gives every record the required fields', () => {
    for (const m of MEASUREMENT_REGISTRY) {
      expect(m.key).toBeTruthy()
      expect(m.displayName).toBeTruthy()
      expect(m.startPoint).toBeTruthy()
      expect(m.tapeInstructions).toBeTruthy()
      expect(m.sources.length).toBeGreaterThan(0)
      expect(m.captureViews.length).toBeGreaterThan(0)
      expect(['circumference', 'straight', 'surface']).toContain(m.path)
      expect(['core', 'future']).toContain(m.scope)
    }
  })

  it('marks circumferences with an empty end point', () => {
    for (const m of MEASUREMENT_REGISTRY) {
      if (m.path === 'circumference') expect(m.endPoint).toBe('')
    }
  })

  it('keeps every record a body measurement (no ease/allowance)', () => {
    expect(BODY_MEASUREMENT_POLICY).toMatch(/no garment ease/i)
    for (const m of MEASUREMENT_REGISTRY) {
      expect(m.tapeInstructions.toLowerCase()).not.toMatch(/\bease\b|\ballowance\b/)
      expect(m.startPoint.toLowerCase()).not.toMatch(/\bease\b|\ballowance\b/)
    }
  })
})

describe('owner corrections', () => {
  it('corrects full front length to start at the side neck point', () => {
    const m = getMeasurement('full_front_length')!
    expect(m.startPoint).toBe('Side neck point')
    expect(m.ownerCorrections.join(' ')).toMatch(/side neck point/i)
    expect(m.sources.map((s) => s.quote).join(' ')).toMatch(/front neck point/i)
    expect(m.path).toBe('surface')
  })

  it("records the men's full front length endpoint as the cord on the waist", () => {
    const m = getMeasurement('full_front_length')!
    expect(m.endPoint).toBe('Cord on the waist (front)')
    expect(m.ownerCorrections.join(' ')).toMatch(/cord on the waist/i)
    expect(m.tapeInstructions).toMatch(/cord on the waist/i)
    expect(m.ambiguities).toEqual([])
  })

  it('corrects side waist to knee to the side (not centre front)', () => {
    const m = getMeasurement('side_waist_to_knee')!
    expect(m.scope).toBe('future')
    expect(m.startPoint).toMatch(/side/i)
    expect(m.tapeInstructions).toMatch(/side/i)
    expect(m.ownerCorrections.join(' ')).toMatch(/centre-front wording/i)
  })
})

describe('owner-confirmed definitions', () => {
  it('bust point length: side neck point to the fullest point of the bust, not vertical', () => {
    const m = getMeasurement('bust_point')!
    expect(m.startPoint).toBe('Side neck point')
    expect(m.endPoint).toBe('Fullest point of the bust')
    expect(m.path).toBe('surface')
    expect(m.tapeInstructions).toMatch(/fullest point of the bust/i)
    expect(m.tapeInstructions).not.toMatch(/vertical/i)
    expect(m.tapeInstructions).not.toMatch(/nipple/i)
    expect(m.ambiguities).toEqual([])
  })

  it('bust radius: downward from the fullest point of the bust to the underbust', () => {
    const m = getMeasurement('bust_radius')!
    expect(m.startPoint).toBe('Fullest point of the bust')
    expect(m.endPoint).toMatch(/underneath the bust/i)
    expect(m.path).toBe('straight')
    expect(m.tapeInstructions).toMatch(/downward/i)
    expect(m.ambiguities).toEqual([])
  })

  it('front shoulder: straight across, tape resting against the body', () => {
    const m = getMeasurement('front_shoulder')!
    expect(m.path).toBe('straight')
    expect(m.tapeInstructions).toMatch(/straight across the front/i)
    expect(m.tapeInstructions).toMatch(/resting against the body/i)
  })

  it('back shoulder: follows the shoulder curvature', () => {
    const m = getMeasurement('back_shoulder')!
    expect(m.path).toBe('surface')
    expect(m.tapeInstructions).toMatch(/shoulder curvature/i)
  })

  it('nape to waist: straight down the centre back to the cord', () => {
    const m = getMeasurement('nape_to_waist')!
    expect(m.endPoint).toMatch(/cord/i)
    expect(m.path).toBe('straight')
    expect(m.tapeInstructions).toMatch(/straight down the centre back/i)
    expect(m.tapeInstructions).toMatch(/cord/i)
  })

  it('across chest and back: 4 in (101.6 mm) below the shoulder point', () => {
    const chest = getMeasurement('across_chest')!
    const back = getMeasurement('across_back')!
    expect(chest.path).toBe('surface')
    expect(back.path).toBe('surface')
    expect(chest.tapeInstructions).toMatch(/4 inches \(101\.6 mm\) below the shoulder point/i)
    expect(back.tapeInstructions).toMatch(/4 inches \(101\.6 mm\) below the shoulder point/i)
    expect(chest.ambiguities).toEqual([])
    expect(back.ambiguities).toEqual([])
  })

  it('bust span: bust point = fullest point of the bust = bust apex', () => {
    const m = getMeasurement('bust_span')!
    expect(m.startPoint).toBe('Fullest point of the bust (one side)')
    expect(m.endPoint).toBe('Fullest point of the bust (other side)')
    expect(m.ownerCorrections.join(' ')).toMatch(/bust apex/i)
    expect(m.ambiguities).toEqual([])
  })
})

describe('integration mappings', () => {
  it('maps every record to a CoStudio key', () => {
    const costudio = Object.fromEntries(MEASUREMENT_REGISTRY.map((m) => [m.key, m.mapping.costudioKey]))
    expect(costudio.bust).toBe('bust')
    expect(costudio.underbust).toBe('under_bust')
    expect(costudio.bust_point).toBe('bust_point')
    expect(costudio.bust_span).toBe('bust_span')
    expect(costudio.bust_radius).toBe('bust_radius')
    expect(costudio.waist).toBe('waist')
    expect(costudio.front_shoulder).toBe('front_shoulder')
    expect(costudio.back_shoulder).toBe('back_shoulder')
    expect(costudio.across_chest).toBe('across_chest')
    expect(costudio.across_back).toBe('across_back')
    expect(costudio.nape_to_waist).toBe('nape_to_waist')
    expect(costudio.full_front_length).toBe('full_front_length')
    expect(costudio.side_waist_to_knee).toBe('side_waist_to_knee')
  })

  it('maps directly to Pattern CAD body landmarks where they exist', () => {
    expect(getMeasurement('bust')!.mapping.patternCadLandmark).toBe('bust')
    expect(getMeasurement('underbust')!.mapping.patternCadLandmark).toBe('underBust')
    expect(getMeasurement('waist')!.mapping.patternCadLandmark).toBe('waist')
    expect(getMeasurement('front_shoulder')!.mapping.patternCadLandmark).toBe('shoulder')
    expect(getMeasurement('back_shoulder')!.mapping.patternCadLandmark).toBe('shoulder')
    expect(getMeasurement('across_chest')!.mapping.patternCadLandmark).toBe('acrossChest')
    expect(getMeasurement('nape_to_waist')!.mapping.patternCadLandmark).toBe('napeToWaist')
    expect(getMeasurement('side_waist_to_knee')!.mapping.patternCadLandmark).toBe('sideWaistToKnee')
  })

  it('stores every measurement as a named row; extra ones do not drive a morph landmark', () => {
    // Pattern CAD stores the user's .mtb measurement table by name — nothing is hardcoded,
    // so every measurement has a storable name.
    for (const m of MEASUREMENT_REGISTRY) {
      expect(m.mapping.patternCadNames.length).toBeGreaterThan(0)
    }
    // Measurements that are stored but do not currently drive a 3D morph landmark.
    const nonMorph = MEASUREMENT_REGISTRY.filter((m) => m.mapping.patternCadLandmark === null).map(
      (m) => m.key,
    )
    expect(nonMorph.sort()).toEqual(
      ['across_back', 'bust_point', 'bust_radius', 'bust_span', 'full_front_length'].sort(),
    )
  })
})
