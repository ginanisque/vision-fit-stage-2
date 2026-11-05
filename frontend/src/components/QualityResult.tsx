import type { QualityDecision } from '../types'

interface Props {
  previews?: { front: string | null; side: string | null; back: string | null }
  results: QualityDecision[]
  checking: boolean
  error: string | null
  onCheck: () => void
  onRetake: (view: 'front' | 'side' | 'back') => void
  captureSessionId?: string
  onDelete?: () => void
}

export function QualityResult({
  results, checking, error, onCheck, onRetake, previews, captureSessionId, onDelete,
}: Props) {
  if (results.length === 0) {
    return (
      <section className="step">
        <h1>Quality check</h1>
        <p>We will check exposure, blur, silhouette framing and possible waist-cord bands on all three images.</p>
        <p className="muted">
          Posture, camera position and natural-waist placement require review. A detected band may be clothing trim.
        </p>
        <div className="actions">
          <button className="primary" disabled={checking} onClick={onCheck}>
            {checking ? 'Checking…' : 'Check quality'}
          </button>
        </div>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      </section>
    )
  }

  const allProceed = results.every((r) => r.decision === 'proceed')
  return (
    <section className="step">
      <h1>{allProceed ? 'Quality passed' : results.some(r => r.decision === 'recapture') ? 'Recapture needed' : 'Review needed'}</h1>
      <ul className="results">
        {results.map((r) => (
          <li key={r.id} className={r.decision === 'proceed' ? 'result-pass' : 'result-fail'}>
            <strong>{r.view}</strong>: {r.decision}
            {previews?.[r.view] && (
              <div className="capture-evidence">
                <img src={previews[r.view]!} alt={`${r.view} capture with evidence`} />
                <svg viewBox={`0 0 ${r.dimensions.width} ${r.dimensions.height}`} aria-label={`${r.view} detected evidence`}>
                  {(r.evidence ?? []).map((e, i) => {
                    const color = e.kind === 'cord-candidate' ? '#ffcc00' : '#00e0ff'
                    const stroke = Math.max(2, r.dimensions.width / 200)
                    return (
                      <g key={i}>
                        <title>{e.label}</title>
                        {e.kind === 'pose-landmark' ? (
                          <circle cx={e.box.x} cy={e.box.y} r={Math.max(2, r.dimensions.width / 160)}
                            fill="none" stroke={color} strokeWidth={stroke / 2} />
                        ) : (
                          <rect {...e.box} fill="none" stroke={color} strokeWidth={stroke} />
                        )}
                      </g>
                    )
                  })}
                </svg>
              </div>
            )}
            {r.captureChecks && <ul>{Object.entries(r.captureChecks).map(([name, check]) => {
              const posture = name === 'posture' ? check : undefined
              const detail = posture?.orientation
                ? ` — view ${posture.orientation}, head-to-feet ${posture.headToFeet}, posture ${posture.postureQuality}`
                : ''
              return <li key={name}>{name}: {check.status}{detail} — {check.method}</li>
            })}</ul>}
            {r.reasons.length > 0 && (
              <ul>
                {r.reasons.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>

      {allProceed ? (
        <p className="success">Image quality is acceptable.</p>
      ) : (
        <p className="error" role="alert">
          Follow the requests above. These still photos are reference evidence only; measurement estimates come from the slow-turn video.
        </p>
      )}

      {!allProceed && (
        <div className="actions">
          {results
            .filter((r) => r.decision !== 'proceed')
            .map((r) => (
              <button key={r.view} className="secondary" onClick={() => onRetake(r.view)}>
                Retake {r.view}
              </button>
            ))}
        </div>
      )}

      {error && <p role="alert" className="error">{error}</p>}
      <button className="secondary" disabled={checking} onClick={onCheck}>{checking ? 'Checking…' : 'Recheck captures'}</button>
      {captureSessionId && onDelete && (
        <button className="secondary" disabled={checking} onClick={onDelete}>Delete my capture data</button>
      )}
      <p className="muted">
        Cyan shows a contrast silhouette candidate; yellow shows a possible waist cord. These are not anatomical landmarks.
      </p>
      <p className="muted">
        This decision is recorded with provenance (image fingerprint, metrics and provisional
        thresholds).
      </p>
    </section>
  )
}
