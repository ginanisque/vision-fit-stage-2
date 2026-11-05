import type { QualityDecision } from '../types'

interface Props {
  records: QualityDecision[]
}

export function DecisionLog({ records }: Props) {
  if (records.length === 0) return null
  return (
    <section className="decision-log">
      <h2>Decision log ({records.length})</h2>
      <ol>
        {records.map((r) => (
          <li key={r.id}>
            <span className={`badge ${r.decision}`}>{r.decision}</span> {r.view} ·{' '}
            {new Date(r.checkedAt).toLocaleTimeString()} · sha {r.imageFingerprint.sha256.slice(0, 12)}
          </li>
        ))}
      </ol>
    </section>
  )
}
