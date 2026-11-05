import type { LengthUnit } from './types'

/**
 * Millimetres per display unit — mirrors Ginani Pattern CAD's
 * `MILLIMETRES_PER_UNIT` (references/ginani-pattern-cad/src/shared/lib/index.ts).
 * Pattern CAD stores geometry/measurements canonically in millimetres.
 */
export const MILLIMETRES_PER_UNIT: Readonly<Record<LengthUnit, number>> = {
  mm: 1,
  cm: 10,
  in: 25.4,
}

export const LENGTH_UNITS: readonly LengthUnit[] = ['mm', 'cm', 'in']

export function lengthToMillimetres(value: number, unit: LengthUnit): number {
  return value * MILLIMETRES_PER_UNIT[unit]
}

export function millimetresToLengthUnit(value: number, unit: LengthUnit): number {
  return value / MILLIMETRES_PER_UNIT[unit]
}

export function convertLength(value: number, from: LengthUnit, to: LengthUnit): number {
  return millimetresToLengthUnit(lengthToMillimetres(value, from), to)
}
