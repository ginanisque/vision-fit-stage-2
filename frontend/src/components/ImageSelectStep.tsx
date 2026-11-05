import { useRef } from 'react'
import { CAMERA_GUIDANCE, CLOTHING_GUIDANCE, CORD_GUIDANCE } from '../lib/guidance'

interface Props {
  view: 'front' | 'side' | 'back'
  preview: string | null
  onSelect: (file: File | null) => void
  onBack: () => void
  onContinue: () => void
}

export function ImageSelectStep({ view, preview, onSelect, onBack, onContinue }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const title = `${view[0].toUpperCase()}${view.slice(1)} photo`

  return (
    <section className="step">
      <h1>{title}</h1>
      <div className="guide">
        <h2>Clothing</h2>
        <ul>
          {CLOTHING_GUIDANCE.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
        <h2>Waist cord</h2>
        <ul>
          {CORD_GUIDANCE.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
        <h2>Camera</h2>
        <ul>
          {CAMERA_GUIDANCE.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </div>

      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        hidden
        aria-label={`${view} image input`}
        onChange={(e) => onSelect(e.target.files?.[0] ?? null)}
      />

      <div className="preview">
        {preview ? (
          <img src={preview} alt={`${title} preview`} />
        ) : (
          <div className="preview-empty">No {view} image selected</div>
        )}
      </div>

      <div className="actions">
        <button className="secondary" onClick={onBack}>
          Back
        </button>
        <button className="secondary" onClick={() => inputRef.current?.click()}>
          {preview ? 'Replace' : 'Choose'} {view} image
        </button>
        <button className="primary" disabled={!preview} onClick={onContinue}>
          Continue
        </button>
      </div>
    </section>
  )
}
