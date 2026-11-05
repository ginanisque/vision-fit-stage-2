import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MeasurementPathEditor } from './MeasurementPathEditor'
import { getMeasurementPaths, saveMeasurementPathDraft } from '../lib/api'

vi.mock('../lib/api', () => ({
  getMeasurementPaths: vi.fn(), saveMeasurementPathDraft: vi.fn(), publishMeasurementPath: vi.fn(),
}))

const path = {
  id: 'v1', measurementKey: 'full_front_length', displayName: 'Full front length',
  version: 1, status: 'published' as const, path: 'surface' as const, closed: false,
  orderedPoints: ['left_side_neck', 'left_bust_apex', 'left_front_waist_below_bust'],
  segmentViews: ['front', 'front'] as Array<'front'>,
  requiredViews: ['front', 'side'] as Array<'front' | 'side'>,
  calculationMethod: 'surface_path', publishedAt: '2026-10-24T00:00:00Z',
}

describe('MeasurementPathEditor', () => {
  beforeEach(() => {
    vi.mocked(getMeasurementPaths).mockResolvedValue([path])
    vi.mocked(saveMeasurementPathDraft).mockResolvedValue({ ...path, version: 2, status: 'draft' })
  })

  it('saves the administrator-defined point order', async () => {
    const user = userEvent.setup()
    render(<MeasurementPathEditor definitions={[{
      key: 'full_front_length', displayName: 'Full front length', scope: 'core', category: 'Vertical length',
      path: 'surface', requiredViews: ['front', 'side'], requiredLandmarks: path.orderedPoints,
      calculation: 'surface_path',
    }]} />)
    await screen.findAllByText('left_bust_apex')
    const downButtons = screen.getAllByRole('button', { name: '↓' })
    await user.click(downButtons[0])
    await user.click(screen.getByRole('button', { name: 'Save draft' }))
    await waitFor(() => expect(saveMeasurementPathDraft).toHaveBeenCalledWith(
      'full_front_length', expect.objectContaining({
        orderedPoints: ['left_bust_apex', 'left_side_neck', 'left_front_waist_below_bust'],
      }),
    ))
  })
})
