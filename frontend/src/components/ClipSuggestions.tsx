import { useEffect, useRef, useState } from 'react'
import type { ClipCandidate, Segment, Service } from '../api'
import { formatTime, parseTime } from '../subtitleLayout'
import Section from './Section'

interface Props {
  service: Service
  sourceUrl: string
  disabled: boolean
  onChange: (candidates: ClipCandidate[]) => void
}

/** Minutes:seconds, for the timeline scale. */
function clock(seconds: number): string {
  const m = Math.floor(seconds / 60)
  return `${m}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`
}

/** The suggestions, with a timeline showing where each fragment sits in the service. */
export default function ClipSuggestions({ service, sourceUrl, disabled, onChange }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [previewing, setPreviewing] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [time, setTime] = useState(0)
  const duration = service.sourceInfo?.duration ?? 1
  const segments = service.transcriptData?.segments ?? []

  const update = (id: string, patch: Partial<ClipCandidate>) =>
    onChange(service.candidates.map((c) => (c.id === id ? { ...c, ...patch } : c)))

  // Play only the candidate's own range of the recording.
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

  const jump = (cand: ClipCandidate) => {
    preview(cand)
    document.getElementById(`f-${cand.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  const active = service.candidates.find((c) => c.id === previewing)

  return (
    <Section
      title="Voorgestelde fragmenten"
      intro="De balk laat zien waar elk voorstel in de dienst zit; klik erop om het te horen. Vink aan wat je wilt gebruiken en schuif begin of einde bij als dat nodig is."
      aside={<span className="meta">{service.candidates.length} voorstellen</span>}
    >
      <div className="timeline">
        <div className="rail">
          {service.candidates.map((cand) => (
            <button
              key={cand.id}
              className={`mark ${cand.selected ? 'on' : ''} ${previewing === cand.id ? 'now' : ''}`}
              style={{ left: `${(cand.start / duration) * 100}%`, width: `${Math.max(0.6, ((cand.end - cand.start) / duration) * 100)}%` }}
              onClick={() => jump(cand)}
              title={`${cand.title} · ${formatTime(cand.start)} tot ${formatTime(cand.end)}`}
            />
          ))}
          <span className="head" style={{ left: `${(time / duration) * 100}%` }} />
        </div>
        <div className="ticks">
          {[0, 0.25, 0.5, 0.75, 1].map((f) => (
            <span key={f} className="tc muted">{clock(duration * f)}</span>
          ))}
        </div>
      </div>

      <div className="player">
        <video ref={videoRef} src={sourceUrl} preload="metadata" playsInline controls />
        <p className="meta" style={{ marginTop: '0.35rem' }}>
          {active
            ? `Fragment ${active.id.replace('candidate-', '')} speelt · stopt om ${formatTime(active.end)}`
            : 'Klik op een balkje hierboven of op Beluister bij een fragment.'}
        </p>
      </div>

      <div>
        {service.candidates.map((cand, index) => {
          const excerpt = segments.filter((s) => s.end > cand.start && s.start < cand.end)
          const open = expanded === cand.id
          return (
            <article
              key={cand.id}
              id={`f-${cand.id}`}
              className={`suggestion ${cand.selected ? 'chosen' : ''} ${previewing === cand.id ? 'playing' : ''}`}
            >
              <header>
                <span className="no">{String(index + 1).padStart(2, '0')}</span>
                <div className="head-main">
                  <h3>{cand.title}</h3>
                  <span className="meta tc">{formatTime(cand.start)} – {formatTime(cand.end)}</span>
                  <span className="meta"> · {Math.round(cand.end - cand.start)} sec</span>
                </div>
                <button
                  className={`pick ${cand.selected ? 'on' : ''}`}
                  aria-pressed={cand.selected}
                  disabled={disabled}
                  onClick={() => update(cand.id, { selected: !cand.selected })}
                >
                  {cand.selected ? '✓ Gekozen' : 'Kies dit'}
                </button>
              </header>

              {excerpt.length > 0 && (
                <blockquote className="quote">
                  {open ? excerpt.map((s) => s.text.trim()).join(' ') : shorten(excerpt, 190)}
                </blockquote>
              )}
              {cand.summary && <p>{cand.summary}</p>}
              {cand.reason && <p className="why">{cand.reason}</p>}

              <div className="acts">
                <button className="small" onClick={() => preview(cand)}>{previewing === cand.id ? '■ Stop' : '▶ Beluister'}</button>
                <button className="small" onClick={() => setExpanded(open ? null : cand.id)}>
                  {open ? 'Verberg tekst en tijden' : 'Tekst en tijden'}
                </button>
              </div>

              {open && (
                <div className="trim">
                  <Boundary
                    label="Begin"
                    value={cand.start}
                    min={0}
                    max={cand.end - 1}
                    disabled={disabled}
                    onChange={(t) => update(cand.id, { start: t })}
                    onJump={() => videoRef.current && (videoRef.current.currentTime = cand.start)}
                  />
                  <Boundary
                    label="Einde"
                    value={cand.end}
                    min={cand.start + 1}
                    max={duration}
                    disabled={disabled}
                    onChange={(t) => update(cand.id, { end: t })}
                    onJump={() => videoRef.current && (videoRef.current.currentTime = Math.max(cand.start, cand.end - 3))}
                  />
                  {cand.alternateBoundaries.length > 0 && (
                    <div className="row">
                      <span>Anders</span>
                      {cand.alternateBoundaries.map((alt, i) => (
                        <button key={i} className="small" disabled={disabled} onClick={() => update(cand.id, { start: alt.start, end: alt.end })}>
                          {formatTime(alt.start)} – {formatTime(alt.end)}
                        </button>
                      ))}
                    </div>
                  )}
                  <div className="lines">
                    {excerpt.map((s, i) => (
                      <div key={i}><span className="tc">{formatTime(s.start)}</span> {s.text}</div>
                    ))}
                  </div>
                </div>
              )}
            </article>
          )
        })}
      </div>
    </Section>
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

function Boundary({ label, value, min, max, disabled, onChange, onJump }: BoundaryProps) {
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
  return (
    <div className="row">
      <span>{label}</span>
      <button className="small" disabled={disabled} onClick={() => onChange(clamp(value - 5))}>−5</button>
      <button className="small" disabled={disabled} onClick={() => onChange(clamp(value - 1))}>−1</button>
      <input value={text} disabled={disabled} onChange={(e) => setText(e.target.value)} onBlur={commit} onKeyDown={(e) => e.key === 'Enter' && (e.target as HTMLInputElement).blur()} title="minuten:seconden" />
      <button className="small" disabled={disabled} onClick={() => onChange(clamp(value + 1))}>+1</button>
      <button className="small" disabled={disabled} onClick={() => onChange(clamp(value + 5))}>+5</button>
      <button className="small bare" onClick={onJump} title="Spring hierheen in de speler">▶</button>
    </div>
  )
}
