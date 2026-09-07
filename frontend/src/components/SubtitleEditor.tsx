import { useState } from 'react'
import type { Segment } from '../api'
import { formatTime, parseTime } from '../subtitleLayout'
import Section from './Section'

interface Props {
  segments: Segment[]
  currentTime: number
  onChange: (segments: Segment[]) => void
  onSeek: (time: number) => void
}

export default function SubtitleEditor({ segments, currentTime, onChange, onSeek }: Props) {
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
    const merged = { start: Math.min(a.start, b.start), end: Math.max(a.end, b.end), text: `${a.text.trim()} ${b.text.trim()}`.trim() }
    const next = [...segments]
    next.splice(index, 2, merged)
    onChange(next)
  }

  const remove = (index: number) => onChange(segments.filter((_, i) => i !== index))

  const add = () => {
    const last = segments[segments.length - 1]
    const start = last ? last.end : 0
    onChange([...segments, { start, end: start + 2, text: '' }])
  }

  return (
    <Section
      eyebrow="Ondertitels"
      title="Lees de tekst na"
      intro="De computer heeft de gesproken tekst uitgeschreven, maar maakt soms fouten in namen en Bijbelteksten. Klik in een regel om de tekst te verbeteren. Met ▶ hoor je precies dat stukje. Splitsen maakt een lange regel korter, Samenvoegen plakt twee regels aan elkaar."
    >
      {segments.length === 0 && <p className="empty">Nog geen ondertitels. Klik onderaan op Ondertitels maken, of voeg zelf een regel toe.</p>}
      <div className="segments">
        {segments.map((seg, i) => (
          <div key={i} className={`segment ${currentTime >= seg.start && currentTime < seg.end ? 'active' : ''}`}>
            <div className="times">
              <TimeInput value={seg.start} onCommit={(t) => update(i, { start: t })} />
              <span>tot</span>
              <TimeInput value={seg.end} onCommit={(t) => update(i, { end: t })} />
              <button className="small" title="Speel dit stukje af" onClick={() => onSeek(seg.start)}>▶</button>
              <div className="actions">
                <button className="small" onClick={() => split(i)} disabled={seg.text.trim().split(/\s+/).length < 2} title="Verdeel deze regel in twee regels">Splitsen</button>
                <button className="small" onClick={() => merge(i)} disabled={i >= segments.length - 1} title="Voeg samen met de volgende regel">Samenvoegen ↓</button>
                <button className="small" onClick={() => remove(i)} title="Verwijder deze regel">✕</button>
              </div>
            </div>
            <textarea value={seg.text} rows={2} onChange={(e) => update(i, { text: e.target.value })} lang="nl" spellCheck placeholder="Tekst van deze regel" />
          </div>
        ))}
      </div>
      <div style={{ marginTop: '0.8rem' }}>
        <button className="small" onClick={add}>+ Regel toevoegen</button>
      </div>
    </Section>
  )
}

function TimeInput({ value, onCommit }: { value: number; onCommit: (t: number) => void }) {
  const [text, setText] = useState(formatTime(value))
  const [invalid, setInvalid] = useState(false)
  const [lastValue, setLastValue] = useState(value)
  if (value !== lastValue) {
    // Reset the draft when the segment time changes from outside (split, merge, reload).
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
