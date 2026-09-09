import { useState, type ReactNode } from 'react'
import type { Segment } from '../api'
import { formatTime, parseTime } from '../subtitleLayout'
import Section from './Section'

interface Props {
  segments: Segment[]
  currentTime: number
  onChange: (segments: Segment[]) => void
  onSeek: (time: number) => void
  /** Shown under the script: what the app noticed while you were correcting. */
  children?: ReactNode
}

/** The transcript as a script: timecodes in the left rail, the text reads as one document. */
export default function SubtitleEditor({ segments, currentTime, onChange, onSeek, children }: Props) {
  const update = (index: number, patch: Partial<Segment>) =>
    onChange(segments.map((s, i) => (i === index ? { ...s, ...patch } : s)))

  const split = (index: number) => {
    const seg = segments[index]
    const words = seg.text.trim().split(/\s+/)
    const half = Math.max(1, Math.ceil(words.length / 2))
    const first = words.slice(0, half).join(' ')
    const second = words.slice(half).join(' ')
    const ratio = words.length > 1 ? first.length / seg.text.trim().length : 0.5
    const mid = Math.round((seg.start + (seg.end - seg.start) * ratio) * 100) / 100
    const next = [...segments]
    next.splice(index, 1, { start: seg.start, end: mid, text: first }, { start: mid, end: seg.end, text: second })
    onChange(next)
  }

  const merge = (index: number) => {
    const a = segments[index]
    const b = segments[index + 1]
    const next = [...segments]
    next.splice(index, 2, { start: Math.min(a.start, b.start), end: Math.max(a.end, b.end), text: `${a.text.trim()} ${b.text.trim()}`.trim() })
    onChange(next)
  }

  const add = () => {
    const last = segments[segments.length - 1]
    const start = last ? last.end : 0
    onChange([...segments, { start, end: start + 2, text: '' }])
  }

  return (
    <Section
      step={1}
      title="Ondertitels"
      intro="De computer verstaat namen en Bijbelteksten niet altijd goed. Klik in een regel om de tekst te verbeteren; met ▶ hoor je precies dat stukje terug."
      aside={<span className="meta">{segments.length} regels</span>}
    >
      {segments.length === 0 ? (
        <p className="empty">Nog geen ondertitels. Klik links op Ondertitels maken, of voeg hieronder zelf een regel toe.</p>
      ) : (
        <div className="script">
          {segments.map((seg, i) => (
            <div key={i} className={`take ${currentTime >= seg.start && currentTime < seg.end ? 'active' : ''}`}>
              <div className="when">
                <TimeInput value={seg.start} onCommit={(t) => update(i, { start: t })} />
                <span className="to">tot</span>
                <TimeInput value={seg.end} onCommit={(t) => update(i, { end: t })} />
              </div>
              <div className="body">
                <textarea value={seg.text} rows={1} onChange={(e) => update(i, { text: e.target.value })} lang="nl" spellCheck placeholder="Tekst van deze regel" />
                <div className="tools">
                  <button className="bare small" onClick={() => onSeek(seg.start)} title="Speel dit stukje af">▶ Beluister</button>
                  <button className="bare small" onClick={() => split(i)} disabled={seg.text.trim().split(/\s+/).length < 2} title="Verdeel in twee regels">Splitsen</button>
                  <button className="bare small" onClick={() => merge(i)} disabled={i >= segments.length - 1} title="Plak aan de volgende regel">Samenvoegen</button>
                  <button className="bare small" onClick={() => onChange(segments.filter((_, n) => n !== i))} title="Verwijder deze regel">Verwijderen</button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
      <p style={{ marginTop: '0.7rem' }}>
        <button className="small" onClick={add}>Regel toevoegen</button>
      </p>
      {children}
    </Section>
  )
}

function TimeInput({ value, onCommit }: { value: number; onCommit: (t: number) => void }) {
  const [text, setText] = useState(formatTime(value))
  const [invalid, setInvalid] = useState(false)
  const [lastValue, setLastValue] = useState(value)
  if (value !== lastValue) {
    // Reset the draft when the time changes from outside (split, merge, reload).
    setLastValue(value)
    setText(formatTime(value))
    setInvalid(false)
  }

  const commit = () => {
    const parsed = parseTime(text)
    if (parsed === null) {
      setInvalid(true)
      return
    }
    setInvalid(false)
    if (parsed !== value) onCommit(parsed)
    else setText(formatTime(value))
  }

  return (
    <input
      className={invalid ? 'invalid' : ''}
      value={text}
      onChange={(e) => setText(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => e.key === 'Enter' && (e.target as HTMLInputElement).blur()}
      title="minuten:seconden, bijvoorbeeld 00:03.2"
    />
  )
}
