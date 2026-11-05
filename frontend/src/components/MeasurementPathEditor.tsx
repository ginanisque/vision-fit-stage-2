import { useEffect, useMemo, useState } from 'react'
import type { MeasurementDefinitionDto, MeasurementPathDto } from '../types'
import { getMeasurementPaths, publishMeasurementPath, saveMeasurementPathDraft } from '../lib/api'

type View = 'front' | 'side' | 'back'

function fitSegmentViews(points: string[], closed: boolean, current: View[], fallback: View | undefined): View[] {
  const count = Math.max(0, points.length - 1 + (closed ? 1 : 0))
  return Array.from({ length: count }, (_, index) => current[index] ?? fallback ?? 'front')
}

export function MeasurementPathEditor({ definitions }: { definitions: MeasurementDefinitionDto[] }) {
  const [paths, setPaths] = useState<MeasurementPathDto[]>([])
  const [key, setKey] = useState('')
  const [draft, setDraft] = useState<MeasurementPathDto | null>(null)
  const [newPoint, setNewPoint] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const knownPoints = useMemo(() => [...new Set(paths.flatMap(path => path.orderedPoints))].sort(), [paths])

  const load = () => getMeasurementPaths().then(next => {
    setPaths(next)
    setKey(current => current || definitions[0]?.key || next[0]?.measurementKey || '')
  }).catch(reason => setMessage(reason instanceof Error ? reason.message : String(reason)))

  useEffect(() => { void load() }, [definitions])
  useEffect(() => {
    if (!key) return
    const selected = paths.find(path => path.measurementKey === key && path.status === 'draft')
      ?? paths.find(path => path.measurementKey === key && path.status === 'published')
    setDraft(selected ? { ...selected, orderedPoints: [...selected.orderedPoints], segmentViews: [...selected.segmentViews], requiredViews: [...selected.requiredViews] } : null)
  }, [key, paths])

  const createDraft = () => {
    const definition = definitions.find(item => item.key === key)
    if (!definition) return
    setDraft({
      id: '', measurementKey: definition.key, displayName: definition.displayName,
      version: 1, status: 'draft', path: definition.path,
      closed: definition.path === 'circumference', orderedPoints: [...definition.requiredLandmarks],
      segmentViews: fitSegmentViews(definition.requiredLandmarks, definition.path === 'circumference', [], definition.requiredViews[0]),
      requiredViews: [...definition.requiredViews], calculationMethod: definition.calculation,
      publishedAt: null,
    })
  }

  const update = (changes: Partial<MeasurementPathDto>) => setDraft(current => current ? { ...current, ...changes } : current)
  const move = (index: number, direction: -1 | 1) => {
    if (!draft) return
    const target = index + direction
    if (target < 0 || target >= draft.orderedPoints.length) return
    const points = [...draft.orderedPoints]
    ;[points[index], points[target]] = [points[target], points[index]]
    update({ orderedPoints: points, segmentViews: fitSegmentViews(points, draft.closed, draft.segmentViews, draft.requiredViews[0]) })
  }
  const addPoint = () => {
    const point = newPoint.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '')
    if (!draft || !point || draft.orderedPoints.includes(point)) return
    const points = [...draft.orderedPoints, point]
    update({ orderedPoints: points, segmentViews: fitSegmentViews(points, draft.closed, draft.segmentViews, draft.requiredViews[0]) }); setNewPoint('')
  }
  const toggleView = (view: View) => {
    if (!draft) return
    if (draft.requiredViews.includes(view) && draft.requiredViews.length === 1) return
    const views = draft.requiredViews.includes(view)
      ? draft.requiredViews.filter(item => item !== view)
      : [...draft.requiredViews, view]
    update({ requiredViews: views, segmentViews: draft.segmentViews.map(item => item === view && !views.includes(view) ? views[0] : item) })
  }
  const save = async () => {
    if (!draft) return
    setBusy(true); setMessage('')
    try { await saveMeasurementPathDraft(key, draft); setMessage('Draft saved.'); load() }
    catch (reason) { setMessage(reason instanceof Error ? reason.message : String(reason)) }
    finally { setBusy(false) }
  }
  const publish = async () => {
    if (!window.confirm('Publish this path version? Existing measurement tables will keep their previous version.')) return
    setBusy(true); setMessage('')
    try { await publishMeasurementPath(key); setMessage('Path published.'); load() }
    catch (reason) { setMessage(reason instanceof Error ? reason.message : String(reason)) }
    finally { setBusy(false) }
  }

  return <section className="admin-card path-editor">
    <div className="section-heading"><div><h2>Measurement Path Editor</h2><p className="muted">Define the ordered tailoring keypoints used to calculate each measurement. Names must match the COCO dataset exactly; published versions are immutable.</p></div></div>
    <label className="stacked-field">Measurement
      <select value={key} onChange={event => setKey(event.target.value)}>
        {definitions.map(definition => <option key={definition.key} value={definition.key}>{definition.displayName}</option>)}
      </select>
    </label>
    {!draft && <div className="empty-state"><p>No automated path is published for this measurement.</p><button type="button" className="secondary" onClick={createDraft}>Create future path draft</button></div>}
    {draft && <div className="path-editor-grid">
      <div>
        <label className="stacked-field">Path type
          <select value={draft.path} onChange={event => {
            const path = event.target.value as MeasurementPathDto['path']
            const closed = path === 'circumference'
            update({ path, closed, segmentViews: fitSegmentViews(draft.orderedPoints, closed, draft.segmentViews, draft.requiredViews[0]) })
          }}><option value="straight">Straight</option><option value="surface">Surface</option><option value="circumference">Circumference</option></select>
        </label>
        <label className="stacked-field">Calculation method<input value={draft.calculationMethod} onChange={event => update({ calculationMethod: event.target.value })} /></label>
        <fieldset><legend>Required views</legend>{(['front', 'side', 'back'] as View[]).map(view => <label key={view}><input type="checkbox" checked={draft.requiredViews.includes(view)} onChange={() => toggleView(view)} /> {view}</label>)}</fieldset>
        <p className="muted">Version {draft.version} · {draft.status}{draft.closed ? ' · closed loop' : ' · open path'}</p>
      </div>
      <div>
        <h3>Ordered points</h3>
        <ol className="ordered-points">{draft.orderedPoints.map((point, index) => <li key={point}><code>{point}</code><span><button type="button" onClick={() => move(index, -1)} disabled={index === 0}>↑</button><button type="button" onClick={() => move(index, 1)} disabled={index === draft.orderedPoints.length - 1}>↓</button><button type="button" onClick={() => { const points = draft.orderedPoints.filter(item => item !== point); update({ orderedPoints: points, segmentViews: fitSegmentViews(points, draft.closed, draft.segmentViews, draft.requiredViews[0]) }) }}>Remove</button></span></li>)}</ol>
        {draft.closed && draft.orderedPoints.length > 1 && <p className="path-loop"><code>{draft.orderedPoints[draft.orderedPoints.length - 1]}</code> → <code>{draft.orderedPoints[0]}</code> closes the loop</p>}
        <h3>Segment views</h3>
        <ol className="segment-views">{draft.segmentViews.map((view, index) => {
          const start = draft.orderedPoints[index]
          const end = index + 1 < draft.orderedPoints.length ? draft.orderedPoints[index + 1] : draft.orderedPoints[0]
          return <li key={`${start}-${end}`}><code>{start}</code> → <code>{end}</code><select aria-label={`${start} to ${end} view`} value={view} onChange={event => { const segmentViews = [...draft.segmentViews]; segmentViews[index] = event.target.value as View; update({ segmentViews }) }}>{draft.requiredViews.map(item => <option key={item} value={item}>{item}</option>)}</select></li>
        })}</ol>
        <div className="point-adder"><input list="known-keypoints" value={newPoint} onChange={event => setNewPoint(event.target.value)} placeholder="new_keypoint" /><datalist id="known-keypoints">{knownPoints.map(point => <option key={point} value={point} />)}</datalist><button type="button" onClick={addPoint}>Add point</button></div>
      </div>
    </div>}
    <div className="actions"><button type="button" className="secondary" onClick={save} disabled={busy || !draft}>Save draft</button><button type="button" className="primary" onClick={publish} disabled={busy || draft?.status !== 'draft'}>Publish version</button></div>
    {message && <p role="status" className={message.includes('Could not') ? 'error' : 'muted'}>{message}</p>}
  </section>
}
