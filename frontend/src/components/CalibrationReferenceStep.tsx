import { useRef } from 'react'
import type { CalibrationKind } from '../types'

interface Props {
  kind: CalibrationKind | null
  preview: string | null
  onKind: (kind: CalibrationKind | null) => void
  onSelect: (file: File | null) => void
  onBack: () => void
  onContinue: () => void
}

export function CalibrationReferenceStep({ kind, preview, onKind, onSelect, onBack, onContinue }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  return <section className="step">
    <h1>Optional scale reference</h1>
    <p>Take one extra front photo with a known object, then keep the camera, zoom, resolution, subject position, and posture unchanged for the clean front photo.</p>
    <label htmlFor="calibration-kind">Reference object</label>
    <select id="calibration-kind" value={kind ?? ''} onChange={(event) => {
      onKind((event.target.value || null) as CalibrationKind | null)
      onSelect(null)
    }}>
      <option value="">No reference — use my height</option>
      <option value="a4">A4 sheet (210 × 297 mm)</option>
      <option value="letter">US Letter sheet (8.5 × 11 in)</option>
      <option value="ruler_12in">1-foot / 12-inch ruler</option>
    </select>
    {kind && <>
      <div className="guide"><ul>
        <li>Keep the object flat, straight, fully visible, and close to the torso plane.</li>
        <li>Place it beside the torso where it does not cover the body outline or landmarks.</li>
        <li>{kind === 'ruler_12in' ? 'The ruler endpoints and outline must contrast with the background; markings need not be readable.' : 'Use a rigid, unbent sheet with all four corners visible.'}</li>
      </ul></div>
      <input ref={inputRef} type="file" accept="image/*" hidden aria-label="calibration reference image input"
        onChange={(event) => onSelect(event.target.files?.[0] ?? null)} />
      <div className="preview">{preview ? <img src={preview} alt="Calibration reference preview" /> : <div className="preview-empty">No calibration image selected</div>}</div>
    </>}
    <div className="actions">
      <button className="secondary" onClick={onBack}>Back</button>
      {kind && <button className="secondary" onClick={() => inputRef.current?.click()}>{preview ? 'Replace' : 'Choose'} calibration image</button>}
      <button className="primary" disabled={Boolean(kind && !preview)} onClick={onContinue}>Continue</button>
    </div>
  </section>
}
