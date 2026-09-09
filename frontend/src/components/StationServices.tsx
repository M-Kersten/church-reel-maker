import { useEffect, useState } from 'react'
import { ApiError, serviceApi, type StationServices as Listing } from '../api'
import { openBrand } from '../church'
import { minutes, said } from '../serviceTimes'

interface Props {
  /** The number from the brand, empty when the church has not filled one in. */
  station: string
  /** True while something else on the page is already busy. */
  disabled: boolean
  onPick: (url: string) => void
}

/**
 * The services this church has standing on kerkdienstgemist, so the usual Sunday is one
 * click instead of a trip to another site and a copied address. Without a station number
 * this is where you learn what to fill in and where to find it.
 */
export default function StationServices({ station, disabled, onPick }: Props) {
  const [listing, setListing] = useState<Listing | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(Boolean(station))

  // A different number is a different church, so the parent remounts this with a key and
  // the state starts empty; nothing here has to undo what the last one left behind.
  useEffect(() => {
    if (!station) return
    let alive = true
    serviceApi
      .station(station)
      .then((found) => alive && setListing(found))
      .catch((e) => {
        if (!alive) return
        setListing(null)
        setError(e instanceof ApiError || e instanceof Error ? e.message : String(e))
      })
      .finally(() => alive && setBusy(false))
    return () => {
      alive = false
    }
  }, [station])

  if (!station) {
    return (
      <div className="station empty-station">
        <div>
          <strong>Je diensten hier laten staan?</strong>
          <p className="hint">
            Vul het nummer van je kerk op Kerkdienstgemist in, dan staan de diensten van je eigen
            kerk hier klaar en hoef je er niet meer heen. Het nummer staat in het adres van de
            pagina van je kerk: <span className="tc">kerkdienstgemist.nl/stations/<strong>1341</strong></span>.
          </p>
        </div>
        <div className="row">
          <button className="small" onClick={() => openBrand('church')}>Nummer instellen</button>
          <a href="https://kerkdienstgemist.nl/" target="_blank" rel="noreferrer">Zoek je kerk ↗</a>
        </div>
      </div>
    )
  }

  if (busy && !listing) return <p className="empty">Diensten van je kerk worden opgehaald…</p>

  if (error) {
    return (
      <div className="station">
        <div className="error" style={{ marginBottom: '0.6rem' }}>{error}</div>
        <div className="row">
          <button className="small" onClick={() => openBrand('church')}>Nummer aanpassen</button>
          <a href="https://kerkdienstgemist.nl/" target="_blank" rel="noreferrer">Zoek je kerk ↗</a>
        </div>
      </div>
    )
  }

  if (!listing) return null

  return (
    <div className="station">
      <header>
        <strong>{listing.name}</strong>
        <a href={listing.url} target="_blank" rel="noreferrer">Op kerkdienstgemist ↗</a>
      </header>
      {listing.services.length === 0 ? (
        <p className="hint">Er staan op dit moment geen diensten klaar bij deze kerk.</p>
      ) : (
        <ul>
          {listing.services.map((s) => (
            <li key={s.id}>
              <div className="what">
                <strong>{said(s.when)}</strong>
                <span className="meta">{s.title}{minutes(s.duration) ? ` · ${minutes(s.duration)}` : ''}</span>
              </div>
              <button className="small" disabled={disabled} onClick={() => onPick(s.url)}>Ophalen</button>
            </li>
          ))}
        </ul>
      )}
      <p className="hint">Een oudere dienst? Plak het adres ervan hieronder.</p>
    </div>
  )
}
