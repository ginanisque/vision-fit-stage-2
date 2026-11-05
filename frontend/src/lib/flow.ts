import type { HeightUnit } from '../types'

export const CM_MIN = 120
export const CM_MAX = 230
export const CM_PER_INCH = 2.54

export function parseHeight(value: string): number | null {
  const trimmed = value.trim()
  if (!trimmed) return null
  const parsed = Number(trimmed)
  if (!Number.isFinite(parsed) || parsed <= 0) return null
  return parsed
}

export function heightToCm(value: number, unit: HeightUnit): number {
  return unit === 'cm' ? value : value * CM_PER_INCH
}

/** Returns an error message, or null when the entered height is valid. */
export function validateHeight(value: string, unit: HeightUnit): string | null {
  const parsed = parseHeight(value)
  if (parsed === null) return 'Enter a valid number.'
  const cm = heightToCm(parsed, unit)
  const minIn = (CM_MIN / CM_PER_INCH).toFixed(1)
  const maxIn = (CM_MAX / CM_PER_INCH).toFixed(1)
  if (cm < CM_MIN) return `Height is too small (minimum ${CM_MIN} cm / ${minIn} in).`
  if (cm > CM_MAX) return `Height is too large (maximum ${CM_MAX} cm / ${maxIn} in).`
  return null
}
