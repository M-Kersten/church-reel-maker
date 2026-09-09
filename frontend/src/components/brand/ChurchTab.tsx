import type { ChurchInfo } from '../../api'

interface Props {
  church: ChurchInfo
  onChange: (patch: Partial<ChurchInfo>) => void
}

/**
 * Who the church is. Three fields, and every one of them ends up on screen: the end screen
 * fills {churchName}, {serviceTimes} and {instagram} in with what is typed here.
 */
export default function ChurchTab({ church, onChange }: Props) {
  const station = church.kerkdienstgemistStation.trim()
  const link = station
    ? `https://kerkdienstgemist.nl/stations/${encodeURIComponent(station)}`
    : 'https://kerkdienstgemist.nl/'
  return (
    <>
      <p className="tab-intro">
        Deze gegevens komen op het eindscherm van elke video terecht, via {'{churchName}'},{' '}
        {'{serviceTimes}'} en {'{instagram}'} in de teksten daar.
      </p>
      <div className="fields wide-labels">
        <label htmlFor="bname">Naam kerk</label>
        <input id="bname" value={church.churchName} onChange={(e) => onChange({ churchName: e.target.value })} />

        <label htmlFor="btimes">Diensttijden</label>
        <input
          id="btimes"
          value={church.serviceTimes.join(', ')}
          onChange={(e) => onChange({ serviceTimes: e.target.value.split(',').map((t) => t.trim()).filter(Boolean) })}
          placeholder="10:00 Wittevrouwen, 11:30 Wilhelminapark"
        />
        <p className="hint span">Scheid meerdere tijden met een komma. Ze komen achter elkaar op één regel.</p>

        <label htmlFor="binsta">Instagram</label>
        <input id="binsta" value={church.instagram} onChange={(e) => onChange({ instagram: e.target.value })} placeholder="@jouwkerk" />
      </div>

      <div className="group">
        <h3>Kerkdienstgemist</h3>
        <p className="hint">
          Vul het nummer van je kerk in, dan staan je diensten meteen klaar op de dienstpagina
          en hoef je er niet meer heen. Het nummer staat in het adres van de pagina van je kerk:{' '}
          <span className="tc">kerkdienstgemist.nl/stations/<strong>1341</strong></span>.
        </p>
        <div className="fields wide-labels">
          <label htmlFor="bstation">Stationnummer</label>
          <div className="inline">
            <input
              id="bstation"
              value={church.kerkdienstgemistStation}
              inputMode="numeric"
              style={{ width: '8rem' }}
              onChange={(e) => onChange({ kerkdienstgemistStation: e.target.value.trim() })}
              placeholder="1341"
            />
            <a href={link} target="_blank" rel="noreferrer">
              {church.kerkdienstgemistStation ? 'Pagina van deze kerk openen ↗' : 'Zoek je kerk op kerkdienstgemist ↗'}
            </a>
          </div>
        </div>
      </div>
    </>
  )
}
