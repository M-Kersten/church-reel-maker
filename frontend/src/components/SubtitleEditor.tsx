import { useState } from 'react'
import type { Segment } from '../api'
import { formatTime, parseTime } from '../subtitleLayout'

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
    <section className="panel">
      <h2>Subtitles</h2>
      {segments.length === 0 && <p className="empty">No subtitles yet. Run the transcription or add a segment.</p>}
      <div className="segments">
        {segments.map((seg, i) => (
          <div key={i} className={`segment ${currentTime >= seg.start && currentTime < seg.end ? 'active' : ''}`}>
            <div className="times">
              <TimeInput value={seg.start} onCommit={(t) => update(i, { start: t })} />
              <span>→</span>
              <TimeInput value={seg.end} onCommit={(t) => update(i, { end: t })} />
              <button className="small" title="Jump to this segment" onClick={() => onSeek(seg.start)}>▶</button>
              <div className="actions">
                <button className="small" onClick={() => split(i)} disabled={seg.text.trim().split(/\s+/).length < 2} title="Split into two segments">Split</button>
                <button className="small" onClick={() => merge(i)} disabled={i >= segments.length - 1} title="Merge with the next segment">Merge ↓</button>
                <button className="small" onClick={() => remove(i)} title="Delete segment">✕</button>
              </div>
            </div>
            <textarea value={seg.text} rows={2} onChange={(e) => update(i, { text: e.target.value })} lang="nl" spellCheck />
          </div>
        ))}
      </div>
      <div style={{ marginTop: '0.6rem' }}>
        <button className="small" onClick={add}>+ Add segment</button>
      </div>
    </section>
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
      title="mm:ss.s"
    />
  )
}
