import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { TurnVideo } from './TurnVideo'
import { bearerToken } from '../lib/auth-client'

beforeEach(() => {
  vi.mocked(bearerToken).mockResolvedValue('turn-video-token')
})

afterEach(() => {
  vi.clearAllMocks()
  vi.unstubAllGlobals()
})
describe('slow-turn workflow', () => {
  it('handles unsupported camera recording without processing', async () => {
    const fetchMock = vi.fn(); vi.stubGlobal('fetch', fetchMock)
    render(<TurnVideo consent={true} />)
    await userEvent.click(screen.getByRole('button', { name: 'Record slow turn' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Choose an existing video')
    expect(fetchMock).not.toHaveBeenCalled()
  })
  it('uploads with consent, shows review and clears a replaced result', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ id:'v', view:'turn', decision:'review',durationSeconds:10,samples:[{timeSeconds:1,quality:'pass',reasons:[]}],reasons:['Verify a full turn.'],scope:'Sample quality only.' }) })
    vi.stubGlobal('fetch', fetchMock)
    render(<TurnVideo consent={true} />)
    const user = userEvent.setup()
    await user.upload(screen.getByLabelText(/choose video/i), new File(['video'],'turn.webm',{type:'video/webm'}))
    await user.click(screen.getByRole('button',{name:'Check video'}))
    expect(await screen.findByText(/Video: review/)).toBeInTheDocument()
    expect(bearerToken).toHaveBeenCalledOnce()
    expect(fetchMock.mock.calls[0][0]).toBe('/api/turn-video')
    expect(fetchMock.mock.calls[0][1].headers).toEqual({ Authorization: 'Bearer turn-video-token' })
    expect((fetchMock.mock.calls[0][1].body as FormData).get('consent')).toBe('true')
    await user.click(screen.getByRole('button',{name:'Clear video'}))
    expect(screen.queryByText(/Video: review/)).not.toBeInTheDocument()
    expect(screen.getByRole('button',{name:'Check video'})).toBeDisabled()
  })
  it('shows turn coverage evidence when present', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({
      id: 'v', view: 'turn', decision: 'review', durationSeconds: 12,
      samples: [{ timeSeconds: 1, quality: 'pass', reasons: [] }],
      turnCoverage: { status: 'complete', seenViews: ['front', 'back', 'side'], missingViews: [], orientations: [{ timeSeconds: 1, orientation: 'front' }], method: 'pose-landmark orientation' },
      reasons: ['Confirm a full turn.'], scope: 'coverage.' }) })
    vi.stubGlobal('fetch', fetchMock)
    render(<TurnVideo consent={true} />)
    const user = userEvent.setup()
    await user.upload(screen.getByLabelText(/choose video/i), new File(['video'], 'turn.webm', { type: 'video/webm' }))
    await user.click(screen.getByRole('button', { name: 'Check video' }))
    await screen.findByText(/Video: review/)
    expect(bearerToken).toHaveBeenCalledOnce()
    expect(fetchMock).toHaveBeenCalledWith('/api/turn-video', expect.objectContaining({
      headers: { Authorization: 'Bearer turn-video-token' },
    }))
    const coverage = screen.getByText(/Turn coverage:/)
    expect(coverage.textContent).toContain('complete')
    expect(coverage.textContent).toContain('front, back, side')
  })
  it('displays back measurements in the selected measurement system', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({
      id: 'v', view: 'turn', decision: 'review', durationSeconds: 12, samples: [],
      turnCoverage: {
        status: 'complete', seenViews: ['back'], missingViews: [], orientations: [],
        method: 'pose-landmark orientation',
        backMeasurements: {
          status: 'experimental', method: 'test', warning: 'Check estimate.',
          timeSeconds: 5,
          measurements: [{
            key: 'across_back', displayName: 'Across back',
            value: 35, unit: 'cm', confidence: 0.5, requiresReview: true,
          }],
        },
      },
      reasons: [], scope: 'coverage.',
    }) })
    vi.stubGlobal('fetch', fetchMock)
    render(<TurnVideo consent={true} measurementUnit="in" />)
    const user = userEvent.setup()
    await user.upload(screen.getByLabelText(/choose video/i), new File(['video'], 'turn.webm', { type: 'video/webm' }))
    await user.click(screen.getByRole('button', { name: 'Check video' }))
    expect(await screen.findByText('13.8 in')).toBeInTheDocument()
  })
  it('returns the created capture session to the customer workflow', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({
      id: 'video-run', view: 'turn', decision: 'review', durationSeconds: 12,
      samples: [], reasons: [], scope: 'review',
      captureSessionId: 'capture-session-1',
    }) })
    const onSessionCreated = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    render(<TurnVideo consent={true} onSessionCreated={onSessionCreated} />)
    const user = userEvent.setup()
    await user.upload(screen.getByLabelText(/choose video/i), new File(['video'], 'turn.webm', { type: 'video/webm' }))
    await user.click(screen.getByRole('button', { name: 'Check video' }))
    await screen.findByText(/Video: review/)
    expect(onSessionCreated).toHaveBeenCalledWith('capture-session-1')
  })
  it('shows an actionable message when the service is unreachable', async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'))
    vi.stubGlobal('fetch', fetchMock)
    render(<TurnVideo consent={true} />)
    const user = userEvent.setup()
    await user.upload(screen.getByLabelText(/choose video/i), new File(['video'], 'turn.webm', { type: 'video/webm' }))
    await user.click(screen.getByRole('button', { name: 'Check video' }))
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('Could not reach the analysis service')
    expect(bearerToken).toHaveBeenCalledOnce()
    expect(fetchMock).toHaveBeenCalledWith('/api/turn-video', expect.objectContaining({
      headers: { Authorization: 'Bearer turn-video-token' },
    }))
  })
  it('rejects an oversized video before uploading', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    render(<TurnVideo consent={true} />)
    const user = userEvent.setup()
    const big = new File(['video'], 'turn.webm', { type: 'video/webm' })
    Object.defineProperty(big, 'size', { value: 51 * 1024 * 1024 })
    await user.upload(screen.getByLabelText(/choose video/i), big)
    await user.click(screen.getByRole('button', { name: 'Check video' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/larger than 50 MB/)
    expect(fetchMock).not.toHaveBeenCalled()
  })
  it('submits an optional calibration photo and shows at least five video measurements', async () => {
    const measurements = ['Bust', 'Waist', 'Hip', 'Front shoulder', 'Across chest'].map((displayName, index) => ({
      key: displayName.toLowerCase().replace(/ /g, '_'),
      displayName,
      value: 80 + index,
      unit: 'cm' as const,
      confidence: 0.6,
    }))
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({
      id: 'v', view: 'turn', decision: 'review', durationSeconds: 12, samples: [],
      calibration: {
        status: 'accepted', method: 'known object cross-check; height remains primary',
        disagreementPercent: 2.4,
      },
      measurementEstimates: {
        modelVersion: 'vf3-test', measurementTableId: 'table-1',
        persistedKeys: measurements.map(item => item.key), skippedKeys: [],
        measurements, warning: 'Review required.',
      },
      reasons: [], scope: 'coverage.',
    }) })
    vi.stubGlobal('fetch', fetchMock)
    render(<TurnVideo consent={true} heightMm={1700} />)
    const user = userEvent.setup()
    await user.selectOptions(screen.getByLabelText('Reference object'), 'a4')
    const reference = new File(['image'], 'a4.png', { type: 'image/png' })
    await user.upload(screen.getByLabelText('Calibration photo'), reference)
    await user.upload(screen.getByLabelText(/choose video/i), new File(['video'], 'turn.webm', { type: 'video/webm' }))
    await user.click(screen.getByRole('button', { name: 'Check video' }))
    expect(await screen.findByText('Video measurement estimates')).toBeInTheDocument()
    for (const measurement of measurements) {
      expect(screen.getByText(measurement.displayName)).toBeInTheDocument()
    }
    const body = fetchMock.mock.calls[0][1].body as FormData
    expect(body.get('calibration_kind')).toBe('a4')
    expect(body.get('calibration_reference')).toBe(reference)
  })

})
