import { useEffect, useRef, useState } from 'react'
import { serviceApi, type ClipCandidate, type Service } from '../api'
import { formatTime } from '../subtitleLayout'
import ClipSuggestions from './ClipSuggestions'

const STORAGE_KEY = 'church-reel-maker.service'
const BUSY = new Set(['transcribing', 'analyzing', 'processing'])

const STATUS_LABEL: Record<Service['status'], string> = {
  created: 'Waiting for upload',
  uploaded: 'Uploaded',
  transcribing: 'Transcribing',
  transcribed: 'Transcribed',
  analyzing: 'Analyzing service',
  ready: 'Suggestions ready',
  processing: 'Processing selected clips',
  complete: 'Complete',
  error: 'Error',
}

interface Props {
  onOpenClip: (projectId: string) => void
}

/** Full-service entry point: upload -> transcribe -> analyze -> review candidates -> process. */
export default function ServiceView({ onOpenClip }: Props) {
  const [service, setService] = useState<Service | null>(null)
  const [uploading, setUploading] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const autoChain = useRef(false)
  const dirty = useRef(false)

  const fail = (e: unknown) => setError(e instanceof Error ? e.message : String(e))

  const adopt = (s: Service) => {
    setService(s)
    localStorage.setItem(STORAGE_KEY, s.id)
  }

  // Restore the last service after a reload.
  useEffect(() => {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (!saved) return
    serviceApi.get(saved).then(setService).catch(() => localStorage.removeItem(STORAGE_KEY))
  }, [])

  // Poll while a job runs; chain transcribe -> analyze automatically after an upload.
  useEffect(() => {
    if (!service) return
    if (BUSY.has(service.status)) {
      const handle = setInterval(() => serviceApi.get(service.id).then(setService).catch(fail), 2000)
      return () => clearInterval(handle)
    }
    if (autoChain.current && service.status === 'uploaded') {
      serviceApi.transcribe(service.id).then(setService).catch(fail)
    } else if (autoChain.current && service.status === 'transcribed') {
      autoChain.current = false
      serviceApi.analyze(service.id).then(setService).catch(fail)
    }
  }, [service])

  const upload = async (file: File) => {
    setError(null)
    setUploading(true)
    try {
      const s = service && !service.sourceVideo ? service : await serviceApi.create()
      autoChain.current = true
      adopt(await serviceApi.upload(s.id, file))
    } catch (e) {
      fail(e)
      autoChain.current = false
    } finally {
      setUploading(false)
    }
  }

  const run = (action: (id: string) => Promise<Service>) => {
    if (!service) return
    setError(null)
    action(service.id).then(setService).catch(fail)
  }

  // Candidate edits (selection, boundaries) are saved with a short debounce.
  const changeCandidates = (candidates: ClipCandidate[]) => {
    if (!service) return
    dirty.current = true
    setService({ ...service, candidates })
  }
  useEffect(() => {
    if (!service || !dirty.current) return
    const handle = setTimeout(() => {
      dirty.current = false
      setSaving(true)
      serviceApi.saveCandidates(service.id, service.candidates).catch(fail).finally(() => setSaving(false))
    }, 500)
    return () => clearTimeout(handle)
  }, [service])

  const processSelected = async () => {
    if (!service) return
    setError(null)
    try {
      await serviceApi.saveCandidates(service.id, service.candidates)
      dirty.current = false
      setService(await serviceApi.processSelected(service.id))
    } catch (e) {
      fail(e)
    }
  }

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) void upload(file)
  }

  const busy = service ? BUSY.has(service.status) : false
  const hasVideo = Boolean(service?.sourceVideo && service.sourceInfo)
  const selectedCount = service?.candidates.filter((c) => c.selected).length ?? 0
  const progress = service?.job ? Math.round(service.job.progress * 100) : null

  return (
    <div>
      {error && <div className="error">{error}</div>}

      <label
        className={`dropzone ${dragging ? 'active' : ''}`}
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        style={{ marginBottom: '1.25rem', padding: hasVideo ? '1rem' : undefined }}
      >
        <input type="file" accept="video/*,.mp4,.mov,.m4v,.mkv,.webm" disabled={uploading || busy} onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
        {uploading ? 'Uploading…' : hasVideo ? 'Drop another service recording here to start over' : 'Drop the complete service recording here or click to choose one'}
      </label>

      {service && hasVideo && (
        <>
          <section className={`panel status ${service.status}`}>
            <div className="status-row">
              <div>
                <strong>{service.title}</strong>
                <span className="meta"> · {formatTime(service.sourceInfo!.duration)} · {service.sourceInfo!.width}×{service.sourceInfo!.height}</span>
              </div>
              <div className="status-label">
                {busy && <span className="spinner" />}
                {STATUS_LABEL[service.status]}
                {saving ? ' · saving' : ''}
              </div>
            </div>
            {service.status === 'error' && <div className="error" style={{ marginTop: '0.6rem' }}>{service.error}</div>}
            {busy && (
              <div className="progress">
                <div className="bar"><div style={{ width: `${progress ?? 0}%` }} /></div>
                <div className="label">
                  <span>{service.job?.message ?? STATUS_LABEL[service.status]}</span>
                  <span>{progress !== null ? `${progress}%` : ''}</span>
                </div>
              </div>
            )}
            {!busy && (
              <div className="render-actions" style={{ marginTop: '0.8rem' }}>
                {!service.transcript && <button className="primary" onClick={() => run(serviceApi.transcribe)}>Transcribe</button>}
                {service.transcript && service.candidates.length === 0 && (
                  <button className="primary" onClick={() => run(serviceApi.analyze)}>Analyze service</button>
                )}
                {service.transcript && service.candidates.length > 0 && (
                  <button onClick={() => run(serviceApi.analyze)}>Re-analyze</button>
                )}
                {service.transcript && <button onClick={() => run(serviceApi.transcribe)}>Transcribe again</button>}
              </div>
            )}
          </section>

          {service.clips.length > 0 && (
            <section className="panel">
              <h2>Processed clips</h2>
              <ul className="clips">
                {service.clips.map((clip) => (
                  <li key={clip.projectId}>
                    <span>
                      <strong>{clip.title}</strong>
                      <span className="meta"> · {formatTime(clip.start)} — {formatTime(clip.end)} · {clip.projectId}</span>
                    </span>
                    <button className="small" onClick={() => onOpenClip(clip.projectId)}>Open in editor →</button>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {service.candidates.length > 0 && (
            <ClipSuggestions
              service={service}
              sourceUrl={serviceApi.sourceUrl(service.id)}
              disabled={busy}
              onChange={changeCandidates}
            />
          )}

          {service.candidates.length > 0 && (
            <div className="process-bar">
              <span>{selectedCount} {selectedCount === 1 ? 'clip' : 'clips'} selected</span>
              <button className="primary" disabled={busy || selectedCount === 0} onClick={processSelected}>
                {service.status === 'processing' ? 'Processing…' : 'Process selected clips'}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
