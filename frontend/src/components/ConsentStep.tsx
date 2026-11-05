import type { ConsentState } from '../types'

interface Props {
  consent: ConsentState
  onChange: (next: ConsentState) => void
  onContinue: () => void
}

export function ConsentStep({ consent, onChange, onContinue }: Props) {
  const canContinue = consent.agreed && consent.acknowledged
  return (
    <section className="step">
      <h1>Consent &amp; privacy</h1>
      <p>Before we begin, please confirm you understand how your captures will be used.</p>
      <ul className="privacy-list">
        <li>The slow-turn video is the primary source for experimental, review-only measurement candidates. Optional still photos are reference evidence for human review only.</li>
        <li>Captures are stored privately and are never sold or shared publicly.</li>
        <li>Capture media and linked measurement results are automatically deleted after 30 days. You can delete them sooner after submitting a capture.</li>
        <li>Still photos are not sent to Roboflow and are not used to calculate measurements.</li>
      </ul>
      <label className="check">
        <input
          type="checkbox"
          checked={consent.agreed}
          onChange={(e) => onChange({ ...consent, agreed: e.target.checked })}
        />
        <span>I consent to my slow-turn video being processed for experimental measurement estimates.</span>
      </label>
      <label className="check">
        <input
          type="checkbox"
          checked={consent.acknowledged}
          onChange={(e) => onChange({ ...consent, acknowledged: e.target.checked })}
        />
        <span>I understand why captures are needed and how they will be handled.</span>
      </label>
      <label className="check">
        <input
          type="checkbox"
          checked={consent.training}
          onChange={(e) => onChange({ ...consent, training: e.target.checked })}
        />
        <span>Optional: I consent to my capture images being included in de-identified model-training downloads. Without this opt-in, the captures cannot be downloaded or exported for training.</span>
      </label>
      <div className="actions">
        <button className="primary" disabled={!canContinue} onClick={onContinue}>
          Continue
        </button>
      </div>
    </section>
  )
}
