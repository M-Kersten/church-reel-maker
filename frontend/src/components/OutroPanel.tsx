import { useEffect, useState } from 'react'
import { api, type OutroConfig } from '../api'
import Section from './Section'

const BACKGROUND_LABEL: Record<OutroConfig['background']['type'], string> = {
  solid: 'effen kleur',
  gradient: 'kleurverloop',
  image: 'afbeelding',
}

interface Props {
  outroUrl: string
  /** Called after a rebuild, so the preview reloads the new end screen. */
  onRebuilt: () => void
}

/** Shows the end screen and lets the user rebuild it after editing templates/outro.json. */
export default function OutroPanel({ outroUrl, onRebuilt }: Props) {
  const [config, setConfig] = useState<OutroConfig | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  useEffect(() => {
    api.outroConfig().then(setConfig).catch(() => setConfig(null))
  }, [])

  const rebuild = async () => {
    setBusy(true)
    setError(null)
    setDone(false)
    try {
      setConfig(await api.rebuildOutro())
      onRebuilt()
      setDone(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Section
      step={4}
      title="Afsluiter"
      intro="Elke video eindigt met dit scherm. Kleuren, lettertype en teksten staan in het bestand templates/outro.json; na een wijziging klik je op Vernieuwen."
    >
      <div className="outro-row">
        <video
          src={outroUrl}
          muted
          playsInline
          controls
          preload="auto"
          // show a frame with the text on it instead of a black poster
          onLoadedMetadata={(e) => (e.currentTarget.currentTime = e.currentTarget.duration / 2)}
        />
        <div className="outro-facts">
          {config && (
            <dl>
              <dt>Achtergrond</dt><dd>{BACKGROUND_LABEL[config.background.type]}</dd>
              <dt>Lettertype</dt><dd>{config.font}</dd>
              <dt>Duur</dt><dd>{String(config.duration).replace('.', ',')} seconden</dd>
              <dt>Regels</dt><dd>{config.lines.length}</dd>
            </dl>
          )}
          <button onClick={rebuild} disabled={busy || (config !== null && !config.generate)}>
            {busy ? 'Bezig…' : 'Vernieuwen'}
          </button>
          {done && <p className="hint">De afsluiter is opnieuw gemaakt.</p>}
          {config && !config.generate && <p className="hint">Je gebruikt een eigen video als afsluiter (generate staat op false).</p>}
          {error && <div className="error" style={{ marginTop: '0.7rem', marginBottom: 0 }}>{error}</div>}
        </div>
      </div>
      <p className="hint">Liever je eigen filmpje? Zet het als outro.mp4 in de map templates. Dat blijft staan.</p>
    </Section>
  )
}
