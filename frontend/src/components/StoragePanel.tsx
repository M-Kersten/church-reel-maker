import { useEffect, useState } from 'react'
import { ApiError, api, type StorageItem, type StorageReport } from '../api'

const gb = (mb: number) => (mb >= 1000 ? `${(mb / 1000).toFixed(1)} GB` : `${Math.round(mb)} MB`)

function since(days: number): string {
  if (days < 1) return 'vandaag'
  if (days < 2) return 'gisteren'
  if (days < 14) return `${Math.round(days)} dagen geleden`
  return `${Math.round(days / 7)} weken geleden`
}

/**
 * A church that does this weekly fills a laptop: a recording is a few GB and every clip
 * used to sit next to it. This shows what is taking up room and what letting go of it
 * would cost, in the user's terms rather than in file names.
 */
export default function StoragePanel({ onClose }: { onClose: () => void }) {
  const [report, setReport] = useState<StorageReport | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = () => api.storage().then(setReport).catch((e) => setError(e instanceof ApiError ? e.message : String(e)))
  useEffect(() => {
    load()
  }, [])

  const clean = async (item: StorageItem) => {
    setBusy(item.id)
    setError(null)
    try {
      setReport(await api.cleanOne(item.kind, item.id))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }

  const cleanOld = async () => {
    setBusy('old')
    setError(null)
    try {
      setReport(await api.cleanOld())
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }

  if (!report) return null
  const free = report.items.filter((i) => !i.blocked)

  return (
    <div className="sheet" role="dialog" aria-label="Opruimen">
      <div className="sheet-box">
        <header>
          <div>
            <h2>Opruimen</h2>
            <p className="intro">
              Opnames zijn groot. Je kunt ze weggooien zodra je de fragmenten eruit hebt gehaald;
              de uitgeschreven tekst, de gevonden momenten en je gemaakte video&rsquo;s blijven staan.
            </p>
          </div>
          <button className="bare" onClick={onClose} aria-label="Sluiten">✕</button>
        </header>

        <div className="tally">
          <span><strong>{gb(report.usedMb)}</strong> aan opnames en werkbestanden</span>
          <span className={report.lowDisk ? 'bad' : ''}><strong>{report.freeGb} GB</strong> vrij op de schijf</span>
          {report.keepWeeks > 0 && (
            <span className="meta">Opnames ouder dan {report.keepWeeks} weken ruimt de app zelf op, zodra alle fragmenten gemaakt zijn.</span>
          )}
        </div>

        {error && <div className="error">{error}</div>}

        {report.items.length === 0 ? (
          <p className="say">Er staat niets in de weg. Zodra je een dienst uploadt verschijnt hij hier.</p>
        ) : (
          <ul className="tidy">
            {report.items.map((item) => (
              <li key={`${item.kind}-${item.id}`} className={item.blocked ? 'held' : ''}>
                <div className="what">
                  <strong>{item.title}</strong>
                  <span className="meta">
                    {item.kind === 'service' ? 'opname' : 'fragment'} · {since(item.days)} · {gb(item.mb)}
                  </span>
                  <span className="meta">{item.blocked ? item.blocked : `Blijft staan: ${item.keeps}`}</span>
                </div>
                <button className="small" disabled={Boolean(item.blocked) || busy !== null} onClick={() => clean(item)}>
                  {busy === item.id ? 'Bezig…' : 'Weggooien'}
                </button>
              </li>
            ))}
          </ul>
        )}

        {free.length > 1 && (
          <div className="row" style={{ marginTop: '1rem' }}>
            <button className="primary" disabled={busy !== null} onClick={cleanOld}>
              {busy === 'old' ? 'Bezig…' : `Alles ouder dan ${report.keepWeeks} weken weggooien`}
            </button>
            <span className="meta">{gb(report.oldMb)} vrij te maken</span>
          </div>
        )}
      </div>
    </div>
  )
}
