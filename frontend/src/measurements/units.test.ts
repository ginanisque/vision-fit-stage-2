import { describe, expect, it } from 'vitest'
import {
  LENGTH_UNITS,
  MILLIMETRES_PER_UNIT,
  convertLength,
  lengthToMillimetres,
  millimetresToLengthUnit,
} from './units'

describe('MILLIMETRES_PER_UNIT', () => {
  it('matches Pattern CAD factors', () => {
    expect(MILLIMETRES_PER_UNIT).toEqual({ mm: 1, cm: 10, in: 25.4 })
  })
})

describe('lengthToMillimetres / millimetresToLengthUnit', () => {
  it('converts each unit to millimetres', () => {
    expect(lengthToMillimetres(1, 'mm')).toBe(1)
    expect(lengthToMillimetres(1, 'cm')).toBe(10)
    expect(lengthToMillimetres(1, 'in')).toBe(25.4)
  })

  it('round-trips a value', () => {
    expect(millimetresToLengthUnit(lengthToMillimetres(92.5, 'cm'), 'cm')).toBeCloseTo(92.5)
  })
})

describe('convertLength', () => {
  it('converts between units via millimetres', () => {
    expect(convertLength(1, 'in', 'cm')).toBeCloseTo(2.54)
    expect(convertLength(25.4, 'mm', 'in')).toBeCloseTo(1)
    expect(convertLength(100, 'cm', 'mm')).toBe(1000)
  })

  it('is identity for the same unit', () => {
    expect(convertLength(42, 'cm', 'cm')).toBe(42)
  })
})

describe('LENGTH_UNITS', () => {
  it('lists mm, cm and in', () => {
    expect(LENGTH_UNITS).toEqual(['mm', 'cm', 'in'])
  })
})
