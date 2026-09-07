import { useEffect, useRef, useState } from 'react'
import type { ClipCandidate, Segment, Service } from '../api'
import { formatTime, parseTime } from '../subtitleLayout'

interface Props {
  service: Service
  sourceUrl: string
  disabled: boolean
  onChange: (candidates: ClipCandidate[]) => void
}

/** Ranked list of AI-suggested moments with preview, selection and boundary adjustment. */
export default function ClipSuggestions({ service, sourceUrl, disabled, onChange }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [previewing, setPreviewing] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [time, setTime] = useState(0)
  const duration = service.sourceInfo?.duration ?? 0
  const segments = service.transcriptData?.segments ?? []

  const update = (id: string, patch: Partial<ClipCandidate>) =>
    onChange(service.candidates.map((c) => (c.id === id ? { ...c, ...patch } : c)))

  // Play only the candidate's range of the original recording.
  const preview = (cand: ClipCandidate) => {
    const v = videoRef.current
    if (!v) return
    if (previewing === cand.id && !v.paused) {
      v.pause()
      return
    }
    setPreviewing(cand.id)
    v.currentTime = cand.start
    void v.play().catch(() => undefined)
  }

  useEffect(() => {
    const v = videoRef.current
    if (!v) return
    const onTime = () => {
      setTime(v.currentTime)
      const cand = service.candidates.find((c) => c.id === previewing)
      if (cand && v.currentTime >= cand.end) {
        v.pause()
        v.currentTime = cand.end
      }
    }
    v.addEventListener('timeupdate', onTime)
    return () => v.removeEventListener('timeupdate', onTime)
  }, [previewing, service.candidates])

  const active = service.candidates.find((c) => c.id === previewing)

  return (
    <section className="panel suggestions">
      <h2>Clip Suggestions</h2>
      <p className="meta">
        {service.title} · {formatTime(duration)} · {service.candidates.length} suggestions, best first
      </p>

      <div className="player">
        <video ref={videoRef} src={sourceUrl} preload="metadata" playsInline controls onPause={() => undefined} />
        <div className="meta">
          {active ? `Previewing ${active.id.replace('candidate-', '#')} · ${formatTime(time)} / ends ${formatTime(active.end)}` : 'Click ▶ Preview on a suggestion'}
        </div>
      </div>

      <ol className="candidates">
        {service.candidates.map((cand, index) => {
          const excerpt = segments.filter((s) => s.end > cand.start && s.start < cand.end)
          const open = expanded === cand.id
          return (
            <li key={cand.id} className={`candidate ${cand.selected ? 'selected' : ''} ${previewing === cand.id ? 'previewing' : ''}`}>
              <div className="candidate-head">
                <span className="rank">{String(index + 1).padStart(2, '0')}</span>
                <div className="candidate-main">
                  <h3>{cand.title}</h3>
                  <div className="meta">
                    {formatTime(cand.start)} — {formatTime(cand.end)} · {Math.round(cand.end - cand.start)} sec
                    {cand.alternateBoundaries.length > 0 ? ` · ${cand.alternateBoundaries.length} alternate ${cand.alternateBoundaries.length === 1 ? 'boundary' : 'boundaries'}` : ''}
                  </div>
                </div>
                <label className="select">
                  <input type="checkbox" checked={cand.selected} disabled={disabled} onChange={(e) => update(cand.id, { selected: e.target.checked })} />
                  Select
                </label>
              </div>

              {excerpt.length > 0 && (
                <blockquote className="excerpt">
                  “{open ? excerpt.map((s) => s.text.trim()).join(' ') : shorten(excerpt, 180)}”
                </blockquote>
              )}
              {cand.summary && <p className="summary">{cand.summary}</p>}
              {cand.reason && <p className="reason">{cand.reason}</p>}

              <div className="candidate-actions">
                <button className="small" onClick={() => preview(cand)}>{previewing === cand.id ? '■ Stop' : '▶ Preview'}</button>
                <button className="small" onClick={() => setExpanded(open ? null : cand.id)}>{open ? 'Hide details' : 'Transcript & timecodes'}</button>
              </div>

              {open && (
                <div className="boundaries">
                  <BoundaryEditor
                    label="Start"
                    value={cand.start}
                    min={0}
                    max={cand.end - 1}
                    disabled={disabled}
                    onChange={(t) => update(cand.id, { start: t })}
                    onJump={() => {
                      const v = videoRef.current
                      if (v) v.currentTime = cand.start
                    }}
                  />
                  <BoundaryEditor
                    label="End"
                    value={cand.end}
                    min={cand.start + 1}
                    max={duration}
                    disabled={disabled}
                    onChange={(t) => update(cand.id, { end: t })}
                    onJump={() => {
                      const v = videoRef.current
                      if (v) v.currentTime = Math.max(cand.start, cand.end - 3)
                    }}
                  />
                  {cand.alternateBoundaries.length > 0 && (
                    <div className="alternates">
                      Alternatives:
                      {cand.alternateBoundaries.map((alt, i) => (
                        <button key={i} className="small" disabled={disabled} onClick={() => update(cand.id, { start: alt.start, end: alt.end })}>
                          {formatTime(alt.start)} — {formatTime(alt.end)}
                        </button>
                      ))}
                    </div>
                  )}
                  <div className="timecodes">
                    {excerpt.map((s, i) => (
                      <div key={i} className="timecode">
                        <span className="meta">{formatTime(s.start)}</span> {s.text}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </li>
          )
        })}
      </ol>
    </section>
  )
}

function shorten(segments: Segment[], max: number): string {
  const text = segments.map((s) => s.text.trim()).join(' ')
  return text.length > max ? `${text.slice(0, max).trimEnd()}…` : text
}

interface BoundaryProps {
  label: string
  value: number
  min: number
  max: number
  disabled: boolean
  onChange: (t: number) => void
  onJump: () => void
}

function BoundaryEditor({ label, value, min, max, disabled, onChange, onJump }: BoundaryProps) {
  const [text, setText] = useState(formatTime(value))
  const [lastValue, setLastValue] = useState(value)
  if (value !== lastValue) {
    setLastValue(value)
    setText(formatTime(value))
  }
  const clamp = (t: number) => Math.round(Math.min(max, Math.max(min, t)) * 10) / 10
  const commit = () => {
    const parsed = parseTime(text)
    if (parsed === null) setText(formatTime(value))
    else onChange(clamp(parsed))
  }
  const nudge = (d: number) => onChange(clamp(value + d))
  return (
    <div className="boundary">
      <span className="boundary-label">{label}</span>
      <button className="small" disabled={disabled} onClick={() => nudge(-5)}>-5</button>
      <button className="small" disabled={disabled} onClick={() => nudge(-1)}>-1</button>
      <input value={text} disabled={disabled} onChange={(e) => setText(e.target.value)} onBlur={commit} onKeyDown={(e) => e.key === 'Enter' && (e.target as HTMLInputElement).blur()} title="mm:ss.s" />
      <button className="small" disabled={disabled} onClick={() => nudge(1)}>+1</button>
      <button className="small" disabled={disabled} onClick={() => nudge(5)}>+5</button>
      <button className="small" onClick={onJump} title="Jump the player here">▶</button>
    </div>
  )
}
