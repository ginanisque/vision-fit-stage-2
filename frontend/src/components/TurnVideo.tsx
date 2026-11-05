import { useEffect, useRef, useState } from 'react'
import { submitTurnVideoCheck } from '../lib/api'
import { convertLength } from '../measurements/units'
import type { CalibrationKind, HeightUnit, VideoDecision } from '../types'

/** Backend limit for turn videos (service/app/main.py). */
const MAX_VIDEO_BYTES = 50 * 1024 * 1024

export function TurnVideo({
  consent, sessionId, heightMm, trainingConsent, measurementUnit = 'cm', onSessionCreated, onDelete,
}: {
  consent: boolean
  sessionId?: string
  heightMm?: number
  trainingConsent?: boolean
  measurementUnit?: HeightUnit
  onSessionCreated?: (sessionId: string) => void
  onDelete?: () => void
}) {
  const [file, setFile] = useState<File | null>(null)
  const [url, setUrl] = useState<string | null>(null)
  const [result, setResult] = useState<VideoDecision | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [recording, setRecording] = useState(false)
  const [calibrationKind, setCalibrationKind] = useState<CalibrationKind | ''>('')
  const [calibrationFile, setCalibrationFile] = useState<File | null>(null)
  const video = useRef<HTMLVideoElement>(null)
  const recorder = useRef<MediaRecorder | null>(null)
  const stream = useRef<MediaStream | null>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const mounted = useRef(true)
  useEffect(() => { mounted.current = true; return () => {
    mounted.current = false
    if (recorder.current?.state === 'recording') recorder.current.stop()
    stream.current?.getTracks().forEach(t => t.stop())
    if (timer.current) clearTimeout(timer.current)
  } }, [])
  useEffect(() => { if (!file) { setUrl(null); return }
    const next = URL.createObjectURL(file); setUrl(next)
    return () => URL.revokeObjectURL(next)
  }, [file])
  const stop = () => { if (recorder.current?.state === 'recording') recorder.current.stop() }
  const start = async () => {
    setError(''); setResult(null)
    try {
      if (!consent) throw new Error('Consent is required.')
      if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) throw new Error('Camera recording is unavailable. Choose an existing video instead.')
      const media = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false })
      if (!mounted.current) { media.getTracks().forEach(t => t.stop()); return }
      stream.current = media
      if (video.current) { video.current.srcObject = media; await video.current.play() }
      const parts: Blob[] = []
      const next = new MediaRecorder(media)
      recorder.current = next
      next.ondataavailable = e => { if (e.data.size) parts.push(e.data) }
      next.onstop = () => {
        media.getTracks().forEach(t => t.stop())
        if (timer.current) clearTimeout(timer.current)
        if (video.current) video.current.srcObject = null
        if (mounted.current) {
          setFile(new File(parts, 'slow-turn.webm', { type: next.mimeType || 'video/webm' }))
          setRecording(false)
        }
      }
      next.start(); setFile(null); setRecording(true)
      timer.current = setTimeout(stop, 20000)
    } catch (e) {
      stream.current?.getTracks().forEach(t => t.stop())
      setError(e instanceof Error ? e.message : String(e))
    }
  }
  const check = async () => {
    if (!file || !consent) return
    if (file.size > MAX_VIDEO_BYTES) {
      setError('This video is larger than 50 MB. Record a shorter or lower-resolution slow turn, then try again.')
      return
    }
    setBusy(true); setError(''); setResult(null)
    try {
      const next = await submitTurnVideoCheck(
        file, consent, sessionId, heightMm, trainingConsent,
        calibrationKind && calibrationFile ? { kind: calibrationKind, file: calibrationFile } : undefined,
      )
      setResult(next)
      if (next.captureSessionId) onSessionCreated?.(next.captureSessionId)
    } catch (e) { setError(e instanceof Error ? e.message : String(e)) }
    finally { setBusy(false) }
  }
  return <section className="step turn-video">
    <h1>One slow-turn video</h1>
    <p>Use a helper or fixed camera. Show your head and bare feet with space around them. Keep the camera level, around waist height, without tilting. Step back until your full body fits.</p>
    <p>Stand naturally, shoulders relaxed, feet steady and arms slightly away from your body. Turn once slowly, showing front, both sides and back. Keep the waist cord visible. Recording stops at 20 seconds — longer clips are sampled across the whole turn.</p>
    <details className="guide">
      <summary>Optional: add one calibration photo</summary>
      <p>This is a scale cross-check only—the video and your height remain the primary measurement source. Use the same camera position and zoom, and hold the object flat beside your torso without covering your outline.</p>
      <label>Reference object
        <select value={calibrationKind} onChange={event => {
          setCalibrationKind(event.target.value as CalibrationKind | '')
          setCalibrationFile(null)
        }}>
          <option value="">No calibration photo</option>
          <option value="a4">A4 sheet (210 × 297 mm)</option>
          <option value="letter">US Letter sheet (8.5 × 11 in)</option>
          <option value="ruler_12in">12-inch ruler</option>
        </select>
      </label>
      {calibrationKind && <label>Calibration photo
        <input type="file" accept="image/*" onChange={event => {
          setCalibrationFile(event.target.files?.[0] ?? null)
          setResult(null)
        }} />
      </label>}
      {calibrationFile && <p className="muted">Reference ready: {calibrationFile.name}</p>}
    </details>
    <video ref={video} src={url ?? undefined} controls={!recording} muted playsInline aria-label="Slow-turn video preview" />
    <div className="actions">
      <button onClick={recording ? stop : start} disabled={busy || !consent}>{recording ? 'Stop recording' : 'Record slow turn'}</button>
      <label>Choose video <input type="file" accept="video/mp4,video/webm,video/quicktime" disabled={recording || busy}
        onChange={e => { setFile(e.target.files?.[0] ?? null); setResult(null); setError('') }} /></label>
      <button disabled={!file || busy || recording} onClick={check}>{busy ? 'Checking video…' : 'Check video'}</button>
      <button disabled={recording || busy} onClick={() => { setFile(null); setResult(null); setError('') }}>Clear video</button>
    </div>
    {error && <p role="alert" className="error">{error}</p>}
    {result && <div aria-live="polite"><strong>Video: {result.decision} ({result.durationSeconds}s)</strong>
      <ul>{result.reasons.map(r => <li key={r}>{r}</li>)}</ul>
      {result.turnCoverage && (
        <p>
          Turn coverage: <strong>{result.turnCoverage.status}</strong>
          {result.turnCoverage.seenViews.length > 0 && <> — seen {result.turnCoverage.seenViews.join(', ')}</>}
          {result.turnCoverage.missingViews.length > 0 && <> — missing {result.turnCoverage.missingViews.join(', ')}</>}
          <span className="muted"> ({result.turnCoverage.method})</span>
        </p>
      )}
      {result.turnCoverage?.selectedViewFrames && (
        <p className="muted">
          Selected frames: {(['front', 'side', 'back'] as const)
            .filter(view => result.turnCoverage?.selectedViewFrames?.[view] !== undefined)
            .map(view => `${view} ${result.turnCoverage?.selectedViewFrames?.[view]}s`).join(' · ')}
        </p>
      )}
      {result.calibration && <p className={result.calibration.status === 'accepted' ? 'muted' : result.calibration.status === 'rejected' ? 'error' : 'muted'}>
        Scale reference: <strong>{result.calibration.status.replace('_', ' ')}</strong> — {result.calibration.method}
        {result.calibration.disagreementPercent !== undefined && <> ({result.calibration.disagreementPercent}% difference)</>}
        {result.calibration.reason && <>. {result.calibration.reason}</>}
      </p>}
      {result.measurementEstimates && <section className="estimate-panel" aria-label="Video estimates submitted for review">
        <h3>Video measurement estimates</h3>
        <div className="measurement-grid">
          {result.measurementEstimates.measurements.map(measurement => <article key={measurement.key}>
            <strong>{measurement.displayName}</strong>
            <span>{convertLength(measurement.value, 'cm', measurementUnit).toFixed(1)} {measurementUnit}</span>
            <small>confidence {Math.round(measurement.confidence * 100)}% · review required</small>
          </article>)}
        </div>
        {result.measurementEstimates.persistedKeys.length > 0
          ? <p>{result.measurementEstimates.persistedKeys.length} experimental measurements were saved for an administrator to review and adjust. They are not approved tailoring values.</p>
          : <p>No new measurements were saved. Existing approved values were left unchanged.</p>}
        {result.measurementEstimates.skippedKeys.length > 0 &&
          <p className="muted">{result.measurementEstimates.skippedKeys.length} values were not updated because their table rows are unavailable or already approved.</p>}
        {!!result.measurementEstimates.unavailableMeasurements?.length && <div>
          <h4>Not estimated</h4>
          <ul>{result.measurementEstimates.unavailableMeasurements.map(item =>
            <li key={item.key}>{item.displayName}: {item.reason}</li>)}</ul>
        </div>}
        <p className="muted">{result.measurementEstimates.warning}</p>
      </section>}
      {result.measurementEstimateError && <p className="muted">{result.measurementEstimateError}</p>}
      {sessionId && onDelete && (
        <button className="secondary" disabled={busy || recording} onClick={onDelete}>Delete my capture data</button>
      )}
      {result.turnCoverage?.backMeasurements && <section className="estimate-panel" aria-label="Experimental back measurements">
        <h3>Experimental back measurements</h3>
        <div className="measurement-grid">
          {result.turnCoverage.backMeasurements.measurements.map(measurement => <article key={measurement.key}>
            <strong>{measurement.displayName}</strong>
            <span>{convertLength(measurement.value, 'cm', measurementUnit).toFixed(1)} {measurementUnit}</span>
            <small>confidence {Math.round(measurement.confidence * 100)}% · review required</small>
          </article>)}
        </div>
        <p className="error">{result.turnCoverage.backMeasurements.warning}</p>
        <p className="muted">Extracted from the back-facing frame at {result.turnCoverage.backMeasurements.timeSeconds}s.</p>
      </section>}
      <ul>{result.samples.map(s => <li key={s.timeSeconds}>{s.timeSeconds}s: quality {s.quality}</li>)}</ul>
      <p className="muted">{result.scope}</p>
    </div>}
  </section>
}
