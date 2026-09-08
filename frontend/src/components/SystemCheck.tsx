import { useEffect, useRef, useState } from 'react'
import { api, type Health } from '../api'

/** Shows whether the app has everything it needs. Opens by itself when something is wrong. */
export default function SystemCheck() {
  const [report, setReport] = useState<Health | null>(null)
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)

  // Clicking anywhere else closes the panel.
  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent) => {
      if (!box.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open])

  useEffect(() => {
    let alive = true
    const load = () =>
      api
        .health()
        .then((r) => {
          if (!alive) return
          setReport(r)
          if (!r.ok) setOpen(true)
        })
        .catch(() => alive && setReport(null))
    load()
    const handle = setInterval(load, 60000)
    return () => {
      alive = false
      clearInterval(handle)
    }
  }, [])

  if (!report) return null

  const failing = report.checks.filter((c) => !c.ok)
  return (
    <div className="syscheck" ref={box}>
      <button className={`bare pill ${report.ok ? 'ok' : 'bad'}`} onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className="dot" />
        {report.ok ? 'Alles gereed' : failing.length === 1 ? '1 punt nog niet in orde' : `${failing.length} punten nog niet in orde`}
      </button>
      {open && (
        <ul className="syscheck-list">
          {report.checks.map((c) => (
            <li key={c.name} className={c.ok ? 'ok' : 'bad'}>
              <span className="dot" />
              <strong>{c.name}</strong>
              <span>{c.detail}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
