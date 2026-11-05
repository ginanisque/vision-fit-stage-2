import { describe, expect, it } from 'vitest'
import { heightToCm, parseHeight, validateHeight } from './flow'

describe('parseHeight', () => {
  it('parses valid numbers', () => {
    expect(parseHeight('165')).toBe(165)
    expect(parseHeight(' 165.5 ')).toBe(165.5)
  })

  it('rejects invalid input', () => {
    expect(parseHeight('')).toBeNull()
    expect(parseHeight('abc')).toBeNull()
    expect(parseHeight('-5')).toBeNull()
    expect(parseHeight('0')).toBeNull()
  })
})

describe('heightToCm', () => {
  it('keeps cm unchanged', () => {
    expect(heightToCm(165, 'cm')).toBe(165)
  })

  it('converts inches to cm', () => {
    expect(heightToCm(65, 'in')).toBeCloseTo(165.1)
  })
})

describe('validateHeight', () => {
  it('returns null for a valid height', () => {
    expect(validateHeight('165', 'cm')).toBeNull()
  })

  it('reports invalid numbers', () => {
    expect(validateHeight('abc', 'cm')).toMatch(/valid number/i)
  })

  it('rejects out-of-range heights', () => {
    expect(validateHeight('50', 'cm')).toMatch(/too small/i)
    expect(validateHeight('300', 'cm')).toMatch(/too large/i)
  })
})
