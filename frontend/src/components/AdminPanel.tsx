import { useEffect, useState } from 'react'
import type { AnalysisDecisionDto, CaptureSessionDetailDto, CaptureSessionSummaryDto, CustomerDto, MeasurementDefinitionDto, MeasurementReadinessDto, MeasurementRowDto, MeasurementTableDto } from '../types'
import { createMeasurementTable, exportTrainingData, getAnalysisDecisions, getCaptureMeasurementTable, getCaptureSession, getCaptureSessions, getCustomers, getMeasurementAnalysis, getMeasurementDefinitions, updateMeasurementValue } from '../lib/api'
import { MeasurementPathEditor } from './MeasurementPathEditor'

export function AdminPanel() {
  const [definitions, setDefinitions] = useState<MeasurementDefinitionDto[]>([])
  const [customers, setCustomers] = useState<CustomerDto[]>([])
  const [decisions, setDecisions] = useState<AnalysisDecisionDto[]>([])
  const [sessions, setSessions] = useState<CaptureSessionSummaryDto[]>([])
  const [selectedSessionId, setSelectedSessionId] = useState('')
  const [sessionDetail, setSessionDetail] = useState<CaptureSessionDetailDto | null>(null)
  const [readiness, setReadiness] = useState<MeasurementReadinessDto | null>(null)
  const [subjectId, setSubjectId] = useState('')
  const [table, setTable] = useState<MeasurementTableDto | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)
  const displayRows: Array<MeasurementDefinitionDto & Partial<MeasurementRowDto>> = table?.rows ?? definitions

  useEffect(() => {
    Promise.all([getMeasurementDefinitions(), getCustomers(), getAnalysisDecisions(), getCaptureSessions()])
      .then(([nextDefinitions, nextCustomers, nextDecisions, nextSessions]) => {
        setDefinitions(nextDefinitions)
        setCustomers(nextCustomers)
        setDecisions(nextDecisions)
        setSessions(nextSessions)
        if (nextSessions[0]) {
          setSelectedSessionId(nextSessions[0].id)
          setSubjectId(nextSessions[0].customerId)
        }
      })
      .catch((reason) => setError(reason instanceof Error ? reason.message : String(reason)))
  }, [])

  useEffect(() => {
    if (!selectedSessionId) { setSessionDetail(null); setReadiness(null); setTable(null); return }
    setBusy(true)
    Promise.all([
      getCaptureSession(selectedSessionId),
      getMeasurementAnalysis(selectedSessionId),
      getCaptureMeasurementTable(selectedSessionId),
    ])
      .then(([detail, analysis, linkedTable]) => {
        setSessionDetail(detail)
        setReadiness(analysis)
        setSubjectId(detail.customerId)
        setTable(linkedTable)
      })
      .catch((reason) => setError(reason instanceof Error ? reason.message : String(reason)))
      .finally(() => setBusy(false))
  }, [selectedSessionId])

  const create = async (event: React.FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try { setTable(await createMeasurementTable(subjectId.trim(), selectedSessionId)) }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)) }
    finally { setBusy(false) }
  }

  const downloadTrainingData = async () => {
    setExporting(true)
    setExportError(null)
    try {
      const archive = await exportTrainingData()
      const url = URL.createObjectURL(archive)
      const link = document.createElement('a')
      link.href = url
      link.download = `visionfit-training-consented-${new Date().toISOString().slice(0, 10)}.zip`
      document.body.append(link)
      link.click()
      link.remove()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (reason) {
      setExportError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setExporting(false)
    }
  }

  const saveValue = async (row: MeasurementRowDto, status: 'estimated' | 'reviewed') => {
    const raw = window.prompt(`${row.displayName} value in cm`, row.value == null ? '' : String(row.value))
    if (raw == null) return
    const value = Number(raw)
    if (!Number.isFinite(value) || value <= 0) {
      setError('Enter a positive measurement value.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      setTable(await updateMeasurementValue(
        table!.id, row.key, value, status,
        status === 'reviewed' && row.sourceViews?.length ? row.sourceViews : row.requiredViews,
        row.confidence ?? 0.5,
      ))
    }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)) }
    finally { setBusy(false) }
  }

  return (
    <main className="admin-workspace">
      <section className="admin-hero">
        <div><span className="eyebrow">Restricted workspace</span><h1>Measurement administration</h1></div>
        <p>Review analysis evidence, prepare a customer measurement table, and approve values before export.</p>
      </section>

      <div className="admin-grid">
        <section className="admin-card">
          <h2>Set up measurement table</h2>
          <form onSubmit={create}>
            <label className="stacked-field">Registered person
              <select value={subjectId} onChange={(e) => { setSubjectId(e.target.value); const latest = sessions.find((item) => item.customerId === e.target.value); setSelectedSessionId(latest?.id ?? '') }} required>
                <option value="">Select a registered account</option>
                {customers.map((customer) => <option key={customer.id} value={customer.id}>{customer.displayName || customer.email} · {customer.email} · {customer.captureCount} capture{customer.captureCount === 1 ? '' : 's'}{customer.role === 'admin' ? ' · admin' : ''}</option>)}
              </select>
            </label>
            <label className="stacked-field">Capture session
              <select value={selectedSessionId} onChange={(e) => setSelectedSessionId(e.target.value)} required>
                <option value="">Select captured evidence</option>
                {sessions.filter((item) => item.customerId === subjectId).map((item) => <option key={item.id} value={item.id}>{new Date(item.createdAt).toLocaleString()} · {item.views.join(', ') || 'no assets'} · {item.trainingConsent ? 'training opt-in' : 'review only · not downloadable'} · {item.status}</option>)}
              </select>
            </label>
            <button className="primary" disabled={busy || !subjectId.trim() || !selectedSessionId}>{busy ? 'Loading…' : 'Create linked table'}</button>
          </form>
          {error && <p className="error" role="alert">{error}</p>}
        </section>
        <section className="admin-card summary-card">
          <span className="metric">{definitions.length}</span>
          <span>measurement definitions</span>
          <small>Registry version {table?.registryVersion ?? '1.4.0'}</small>
        </section>
      </div>

      <MeasurementPathEditor definitions={definitions} />

      <section className="admin-card">
        <div className="section-heading">
          <div>
            <h2>Training-data export</h2>
            <p className="muted">Download capture images only from sessions with recorded training consent. The ZIP excludes account details and measurements; images still need labeling before model training.</p>
          </div>
          <button type="button" className="primary" disabled={exporting} onClick={downloadTrainingData}>
            {exporting ? 'Preparing export…' : 'Download consented images'}
          </button>
        </div>
        {exportError && <p className="error" role="alert">{exportError}</p>}
      </section>

      <section className="admin-card capture-review-card">
        <div className="section-heading"><div><h2>Capture review</h2><p className="muted">Private assets are available through short-lived review links. The database stores their keys and analysis metadata.</p></div></div>
        {!sessionDetail && <p className="muted empty-state">Select a registered person and capture session.</p>}
        {sessionDetail && <>
          <div className="capture-summary">
            <div><span>Person</span><strong>{sessionDetail.customerName || sessionDetail.customerEmail}</strong><small>{sessionDetail.customerEmail} · {sessionDetail.customerRole}</small></div>
            <div><span>Captured</span><strong>{new Date(sessionDetail.createdAt).toLocaleString()}</strong><small>{sessionDetail.consentVersion || 'Consent version unavailable'}{sessionDetail.trainingConsent ? ' · training consent' : ''}</small></div>
            <div><span>Height</span><strong>{sessionDetail.heightMm ? `${sessionDetail.heightMm / 10} cm` : 'Missing'}</strong><small>{sessionDetail.assets.length} asset{sessionDetail.assets.length === 1 ? '' : 's'}</small></div>
          </div>
          <div className="capture-assets">
            {sessionDetail.assets.map((asset) => <article key={asset.id} className="capture-asset">
              {!asset.reviewUrl
                ? <p className="muted">Media is unavailable for download because training opt-in was not recorded.</p>
                : asset.contentType.startsWith('image/')
                  ? <img src={asset.reviewUrl} alt={`${asset.view} capture`} />
                  : <video src={asset.reviewUrl} controls preload="metadata" aria-label={`${asset.view} capture`} />}
              <div><strong>{asset.view}</strong><span>{asset.contentType}</span><small>{asset.widthPx && asset.heightPx ? `${asset.widthPx} × ${asset.heightPx}` : asset.durationSeconds ? `${asset.durationSeconds.toFixed(1)} seconds` : ''}</small></div>
            </article>)}
          </div>
          <div className="analysis-evidence">
            {sessionDetail.analysisRuns.map((run) => <article key={run.id}>
              <div><strong>{run.modelName}</strong><span>{run.modelVersion}</span><span className={`status-pill ${String(run.qualityDecision.decision || run.status)}`}>{String(run.qualityDecision.decision || run.status)}</span></div>
              {Array.isArray(run.qualityDecision.reasons) && <ul>{run.qualityDecision.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>}
            </article>)}
          </div>
        </>}
      </section>

      <section className="admin-card table-card measurement-analysis-card">
        <div className="section-heading"><div><h2>Measurement analysis</h2><p className="muted">Evidence readiness is evaluated separately for every measurement. Blocked values are never presented as estimates.</p></div>{readiness && <span className="readiness-count">{readiness.readyCount} ready · {readiness.blockedCount} blocked</span>}</div>
        {readiness && <div className="table-scroll"><table><thead><tr><th>Measurement</th><th>Required views</th><th>Required landmarks</th><th>Readiness</th><th>Missing evidence</th></tr></thead><tbody>
          {readiness.measurements.map((item) => <tr key={item.key}><td><strong>{item.displayName}</strong><small>{item.calculation}</small></td><td>{item.requiredViews.join(' · ')}</td><td>{item.requiredLandmarks.join(' · ')}</td><td><span className={`status-pill ${item.status}`}>{item.status === 'ready_for_estimation' ? 'ready' : item.status === 'manual_required' ? 'manual' : 'blocked'}</span></td><td>{item.status === 'manual_required' ? item.message : [...item.missingViews.map((v) => `${v} view`), ...item.missingLandmarks, ...(item.missingCalibration ? ['height calibration'] : [])].join(', ') || '—'}</td></tr>)}
        </tbody></table></div>}
      </section>

      <section className="admin-card table-card">
        <div className="section-heading"><div><h2>Recent analysis runs</h2><p className="muted">Select a row’s session above to review its private capture evidence and measurement readiness.</p></div></div>
        <div className="table-scroll"><table><thead><tr><th>Customer</th><th>View</th><th>Decision</th><th>Model</th><th>Received</th></tr></thead>
          <tbody>{decisions.map((decision) => <tr key={decision.id}><td>{decision.customerEmail}</td><td>{decision.qualityDecision.view ?? '—'}</td><td><span className={`status-pill ${decision.qualityDecision.decision ?? ''}`}>{decision.qualityDecision.decision ?? decision.status}</span></td><td>{decision.modelName} {decision.modelVersion}</td><td>{new Date(decision.createdAt).toLocaleString()}</td></tr>)}</tbody>
        </table></div>
      </section>

      <section className="admin-card table-card">
        <div className="section-heading"><div><h2>{table ? `Measurement table · ${table.subjectId}` : 'Measurement library'}</h2><p className="muted">Video-derived MediaPipe/OpenCV values are experimental estimates. Review and adjust them against tape measurements before approval.</p></div></div>
        <div className="table-scroll">
          <table>
            <thead><tr><th>Measurement</th><th>Path</th><th>Views</th><th>Value</th><th>Status</th><th>Review</th></tr></thead>
            <tbody>
              {displayRows.map((item) => {
                return <tr key={item.key}><td><strong>{item.displayName}</strong><small>{item.category}</small>{item.method && <small>{item.method}{item.confidence == null ? '' : ` · ${Math.round(item.confidence * 100)}% confidence`}</small>}{item.sourceViews?.length ? <small>Source: {item.sourceViews.join(' · ')}</small> : null}{item.notes && <small>{item.notes}</small>}</td><td>{item.path}</td><td>{item.requiredViews.join(' · ')}</td><td>{item.value == null ? '—' : `${item.value} ${item.unit}`}</td><td><span className={`status-pill ${item.status ?? 'definition'}`}>{item.status ?? 'defined'}</span></td><td>{table && <><button type="button" disabled={busy} onClick={() => saveValue(item as MeasurementRowDto, 'estimated')}>Set estimate</button><button type="button" disabled={busy} onClick={() => saveValue(item as MeasurementRowDto, 'reviewed')}>Adjust &amp; approve</button></>}</td></tr>
              })}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  )
}
