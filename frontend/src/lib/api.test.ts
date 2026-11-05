import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { QualityDecision, VideoDecision } from '../types'
import { deleteCaptureSession, exportTrainingData, submitQualityCheck, submitTurnVideoCheck } from './api'
import { bearerToken } from './auth-client'

const qualityDecision: QualityDecision = {
  id: 'front-1',
  decision: 'proceed',
  view: 'front',
  imageFingerprint: { sha256: 'abc123' },
  dimensions: { width: 400, height: 300 },
  checks: {
    exposure: { status: 'pass', lumaMean: 128, darkClipFraction: 0, brightClipFraction: 0 },
    blur: { status: 'pass', laplacianVariance: 200 },
  },
  reasons: [],
  thresholds: { laplacianVarianceMin: 100 },
  provisionalThresholds: true,
  scope: 'exposure and blur only',
  checkedAt: '2026-10-12T00:00:00Z',
}

function fakeResponse(body: unknown, ok = true, status = 200): Response {
  return {
    ok,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
    blob: async () => new Blob(['archive']),
  } as Response
}

beforeEach(() => {
  vi.mocked(bearerToken).mockResolvedValue('api-test-token')
})

afterEach(() => {
  vi.clearAllMocks()
  vi.unstubAllGlobals()
})

describe('submitQualityCheck', () => {
  it('posts the still photo for reference quality review', async () => {
    const fetchFn = vi.fn().mockResolvedValue(fakeResponse(qualityDecision))
    const file = new File(['fake'], 'front.png', { type: 'image/png' })

    const result = await submitQualityCheck(file, 'front', true, { fetchFn })

    expect(result).toEqual(qualityDecision)
    const body = fetchFn.mock.calls[0][1].body as FormData
    expect(body.get('view')).toBe('front')
    expect(body.get('consent')).toBe('true')
    expect(body.get('file')).toBe(file)
    expect(body.get('external_vision_consent')).toBeNull()
  })

  it('throws on a non-ok response', async () => {
    const fetchFn = vi.fn().mockResolvedValue(fakeResponse({ detail: 'bad' }, false, 400))
    await expect(
      submitQualityCheck(new File(['x'], 'a.png', { type: 'image/png' }), 'front', true, { fetchFn }),
    ).rejects.toThrow(/Quality check failed/)
  })
})

describe('submitTurnVideoCheck', () => {
  const videoDecision: VideoDecision = {
    id: 'v1',
    view: 'turn',
    decision: 'review',
    durationSeconds: 10,
    samples: [{ timeSeconds: 1, quality: 'pass', reasons: [] }],
    reasons: ['Confirm a full turn.'],
    scope: 'sample quality only',
  }

  it('posts the video, consent and optional calibration reference', async () => {
    const fetchFn = vi.fn().mockResolvedValue(fakeResponse(videoDecision))
    vi.stubGlobal('fetch', fetchFn)
    const file = new File(['video'], 'turn.webm', { type: 'video/webm' })
    const reference = new File(['reference'], 'a4.png', { type: 'image/png' })

    const result = await submitTurnVideoCheck(
      file, true, 'session-1', 1650, true, { kind: 'a4', file: reference },
    )

    expect(result).toEqual(videoDecision)
    const body = fetchFn.mock.calls[0][1].body as FormData
    expect(body.get('consent')).toBe('true')
    expect(body.get('session_id')).toBe('session-1')
    expect(body.get('height_mm')).toBe('1650')
    expect(body.get('training_consent')).toBe('true')
    expect(body.get('file')).toBe(file)
    expect(body.get('calibration_kind')).toBe('a4')
    expect(body.get('calibration_reference')).toBe(reference)
  })

  it('turns a network rejection into an actionable message', async () => {
    const fetchFn = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'))
    vi.stubGlobal('fetch', fetchFn)

    await expect(
      submitTurnVideoCheck(new File(['video'], 'turn.webm', { type: 'video/webm' }), true),
    ).rejects.toThrow(/Could not reach the analysis service/)
    expect(bearerToken).toHaveBeenCalledOnce()
  })
})

describe('deleteCaptureSession', () => {
  it('sends an authenticated delete request for the selected capture', async () => {
    const fetchFn = vi.fn().mockResolvedValue(fakeResponse({ deleted: true }))
    vi.stubGlobal('fetch', fetchFn)

    await deleteCaptureSession('session-1')

    expect(fetchFn).toHaveBeenCalledWith('/api/capture-sessions/session-1', expect.objectContaining({
      method: 'DELETE',
      headers: expect.objectContaining({ Authorization: expect.stringMatching(/^Bearer /) }),
    }))
  })
})

describe('exportTrainingData', () => {
  it('downloads the admin training archive with authentication', async () => {
    const fetchFn = vi.fn().mockResolvedValue(fakeResponse({}))
    vi.stubGlobal('fetch', fetchFn)

    const archive = await exportTrainingData()

    expect(await archive.text()).toBe('archive')
    expect(fetchFn).toHaveBeenCalledWith('/api/admin/training-export', expect.objectContaining({
      headers: expect.objectContaining({ Authorization: expect.stringMatching(/^****** }),
    }))
  })

  it('reports an empty or unavailable export clearly', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(fakeResponse(
      { detail: 'No training-consented capture images are available to export' }, false, 404,
    )))

    await expect(exportTrainingData()).rejects.toThrow(/Training-data export failed \(404\)/)
  })
})
